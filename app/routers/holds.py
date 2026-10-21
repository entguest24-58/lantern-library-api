from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import circulation, config
from ..db import transaction
from ..errors import conflict, not_found
from ..security import current_member

router = APIRouter()


class HoldBody(BaseModel):
    book_id: int


def hold_view(conn, hold: dict) -> dict:
    position = None
    if hold["status"] == "waiting":
        position = conn.execute(
            "SELECT count(*) AS n FROM holds WHERE book_id = %s AND status = 'waiting' "
            "AND (created_at, id) <= (%s, %s)",
            (hold["book_id"], hold["created_at"], hold["id"]),
        ).fetchone()["n"]
    return {
        "id": hold["id"],
        "book_id": hold["book_id"],
        "status": hold["status"],
        "created_at": hold["created_at"],
        "ready_until": hold["ready_until"],
        "position": position,
    }


@router.post("/holds", status_code=201)
def place_hold(body: HoldBody, member: dict = Depends(current_member)):
    with transaction() as conn:
        book = circulation.lock_book(conn, body.book_id)
        if book is None:
            raise not_found("book not found")
        circulation.refresh_holds(conn, book)
        if circulation.available_copies(conn, book) > 0:
            raise conflict("a copy is available; borrow it instead")
        if conn.execute(
            "SELECT 1 FROM loans WHERE member_id = %s AND book_id = %s AND returned_at IS NULL",
            (member["id"], book["id"]),
        ).fetchone():
            raise conflict("you already have this book on loan")
        if conn.execute(
            "SELECT 1 FROM holds WHERE member_id = %s AND book_id = %s "
            "AND status IN ('waiting', 'ready')",
            (member["id"], book["id"]),
        ).fetchone():
            raise conflict("you already have a hold on this book")
        active = conn.execute(
            "SELECT count(*) AS n FROM holds WHERE member_id = %s "
            "AND status IN ('waiting', 'ready')",
            (member["id"],),
        ).fetchone()["n"]
        if active >= config.MAX_ACTIVE_HOLDS:
            raise conflict(f"hold limit reached ({config.MAX_ACTIVE_HOLDS} active holds)")
        hold = conn.execute(
            "INSERT INTO holds (member_id, book_id) VALUES (%s, %s) RETURNING *",
            (member["id"], book["id"]),
        ).fetchone()
        return {"hold": hold_view(conn, hold)}


@router.get("/holds")
def list_holds(member: dict = Depends(current_member)):
    with transaction() as conn:
        book_ids = conn.execute(
            "SELECT DISTINCT book_id FROM holds WHERE member_id = %s", (member["id"],)
        ).fetchall()
        for row in book_ids:
            book = circulation.lock_book(conn, row["book_id"])
            circulation.refresh_holds(conn, book)
        holds = conn.execute(
            "SELECT * FROM holds WHERE member_id = %s ORDER BY created_at DESC, id DESC",
            (member["id"],),
        ).fetchall()
        return {"holds": [hold_view(conn, h) for h in holds]}


@router.delete("/holds/{hold_id}")
def cancel_hold(hold_id: int, member: dict = Depends(current_member)):
    with transaction() as conn:
        hold = conn.execute("SELECT * FROM holds WHERE id = %s", (hold_id,)).fetchone()
        if hold is None or hold["member_id"] != member["id"]:
            raise not_found("hold not found")
        if hold["status"] not in ("waiting", "ready"):
            raise conflict(f"hold is already {hold['status']}")
        book = circulation.lock_book(conn, hold["book_id"])
        hold = conn.execute(
            "UPDATE holds SET status = 'cancelled' WHERE id = %s RETURNING *", (hold_id,)
        ).fetchone()
        circulation.refresh_holds(conn, book)
        return {"hold": hold_view(conn, hold)}
