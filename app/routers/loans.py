import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import circulation, config
from ..db import transaction
from ..errors import conflict, forbidden, not_found
from ..security import current_member

router = APIRouter()


class BorrowBody(BaseModel):
    book_id: int


def loan_view(loan: dict) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": loan["id"],
        "member_id": loan["member_id"],
        "book_id": loan["book_id"],
        "borrowed_at": loan["borrowed_at"],
        "due_at": loan["due_at"],
        "returned_at": loan["returned_at"],
        "renewals": loan["renewals"],
        "overdue": loan["returned_at"] is None and loan["due_at"] < now,
    }


def late_fee_cents(due_at: datetime, returned_at: datetime) -> int:
    seconds_late = (returned_at - due_at).total_seconds()
    if seconds_late <= 0:
        return 0
    days_late = math.ceil(seconds_late / 86400)
    return min(days_late * config.LATE_FEE_CENTS_PER_DAY, config.LATE_FEE_CAP_CENTS)


@router.post("/loans", status_code=201)
def borrow(body: BorrowBody, member: dict = Depends(current_member)):
    with transaction() as conn:
        book = circulation.lock_book(conn, body.book_id)
        if book is None:
            raise not_found("book not found")
        circulation.refresh_holds(conn, book)

        active = conn.execute(
            "SELECT count(*) AS n FROM loans WHERE member_id = %s AND returned_at IS NULL",
            (member["id"],),
        ).fetchone()["n"]
        if active >= config.MAX_ACTIVE_LOANS:
            raise conflict(f"loan limit reached ({config.MAX_ACTIVE_LOANS} active loans)")

        unpaid = conn.execute(
            "SELECT coalesce(sum(amount_cents), 0) AS total FROM fees "
            "WHERE member_id = %s AND paid_at IS NULL",
            (member["id"],),
        ).fetchone()["total"]
        if unpaid >= config.BORROW_BLOCK_FEES_CENTS:
            raise conflict("unpaid fees must be settled before borrowing")

        if conn.execute(
            "SELECT 1 FROM loans WHERE member_id = %s AND book_id = %s AND returned_at IS NULL",
            (member["id"], book["id"]),
        ).fetchone():
            raise conflict("you already have this book on loan")

        my_ready_hold = conn.execute(
            "SELECT id FROM holds WHERE member_id = %s AND book_id = %s AND status = 'ready'",
            (member["id"], book["id"]),
        ).fetchone()
        if my_ready_hold:
            conn.execute(
                "UPDATE holds SET status = 'fulfilled' WHERE id = %s", (my_ready_hold["id"],)
            )
        elif circulation.available_copies(conn, book) <= 0:
            raise conflict("no copy available; place a hold instead")

        loan = conn.execute(
            "INSERT INTO loans (member_id, book_id, due_at) "
            "VALUES (%s, %s, now() + make_interval(days => %s)) RETURNING *",
            (member["id"], book["id"], config.LOAN_DAYS),
        ).fetchone()
    return {"loan": loan_view(loan)}


@router.get("/loans")
def list_loans(member_id: int | None = None, member: dict = Depends(current_member)):
    if member_id is not None and member_id != member["id"] and member["role"] != "staff":
        raise forbidden()
    target = member_id if member_id is not None else member["id"]
    with transaction() as conn:
        loans = conn.execute(
            "SELECT * FROM loans WHERE member_id = %s ORDER BY borrowed_at DESC, id DESC",
            (target,),
        ).fetchall()
    return {"loans": [loan_view(l) for l in loans]}


def _load_loan(conn, loan_id: int, member: dict) -> dict:
    loan = conn.execute("SELECT * FROM loans WHERE id = %s FOR UPDATE", (loan_id,)).fetchone()
    if loan is None:
        raise not_found("loan not found")
    if loan["member_id"] != member["id"] and member["role"] != "staff":
        raise not_found("loan not found")
    return loan


@router.post("/loans/{loan_id}/renew")
def renew(loan_id: int, member: dict = Depends(current_member)):
    with transaction() as conn:
        loan = _load_loan(conn, loan_id, member)
        if loan["member_id"] != member["id"]:
            raise forbidden("only the borrower can renew a loan")
        if loan["returned_at"] is not None:
            raise conflict("loan already returned")
        if loan["renewals"] >= 1:
            raise conflict("loan already renewed once")
        if loan_view(loan)["overdue"]:
            raise conflict("overdue loans cannot be renewed")
        waiting = conn.execute(
            "SELECT 1 FROM holds WHERE book_id = %s AND status = 'waiting' LIMIT 1",
            (loan["book_id"],),
        ).fetchone()
        if waiting:
            raise conflict("another member is waiting for this book")
        loan = conn.execute(
            "UPDATE loans SET due_at = due_at + make_interval(days => %s), renewals = renewals + 1 "
            "WHERE id = %s RETURNING *",
            (config.LOAN_DAYS, loan_id),
        ).fetchone()
    return {"loan": loan_view(loan)}


@router.post("/loans/{loan_id}/return")
def return_loan(loan_id: int, member: dict = Depends(current_member)):
    with transaction() as conn:
        loan = _load_loan(conn, loan_id, member)
        if loan["returned_at"] is not None:
            raise conflict("loan already returned")
        book = circulation.lock_book(conn, loan["book_id"])
        loan = conn.execute(
            "UPDATE loans SET returned_at = now() WHERE id = %s RETURNING *", (loan_id,)
        ).fetchone()
        fee_cents = late_fee_cents(loan["due_at"], loan["returned_at"])
        fee = None
        if fee_cents > 0:
            fee = conn.execute(
                "INSERT INTO fees (member_id, loan_id, amount_cents) VALUES (%s, %s, %s) "
                "RETURNING id, amount_cents",
                (loan["member_id"], loan["id"], fee_cents),
            ).fetchone()
        circulation.refresh_holds(conn, book)
    return {"loan": loan_view(loan), "fee": fee}
