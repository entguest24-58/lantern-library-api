"""Copy availability and the hold queue for one book.

A book has `total_copies`. A copy is unavailable while it is on an active loan or set aside
for a ready hold. When a copy frees up and members are waiting, the earliest waiting hold
becomes ready and keeps that copy for HOLD_READY_DAYS.
"""

from . import config


def lock_book(conn, book_id: int) -> dict | None:
    return conn.execute("SELECT * FROM books WHERE id = %s FOR UPDATE", (book_id,)).fetchone()


def counts(conn, book_id: int) -> dict:
    return conn.execute(
        """
        SELECT
          (SELECT count(*) FROM loans WHERE book_id = %(b)s AND returned_at IS NULL) AS on_loan,
          (SELECT count(*) FROM holds WHERE book_id = %(b)s AND status = 'ready') AS ready_holds,
          (SELECT count(*) FROM holds WHERE book_id = %(b)s AND status = 'waiting') AS waiting_holds
        """,
        {"b": book_id},
    ).fetchone()


def available_copies(conn, book: dict) -> int:
    c = counts(conn, book["id"])
    return max(book["total_copies"] - c["on_loan"] - c["ready_holds"], 0)


def refresh_holds(conn, book: dict) -> None:
    """Expire ready holds past their pickup window, then hand free copies to waiting holds."""
    conn.execute(
        "UPDATE holds SET status = 'expired' "
        "WHERE book_id = %s AND status = 'ready' AND ready_until < now()",
        (book["id"],),
    )
    free = available_copies(conn, book)
    if free <= 0:
        return
    conn.execute(
        """
        UPDATE holds SET status = 'ready', ready_until = now() + make_interval(days => %s)
        WHERE id IN (
          SELECT id FROM holds WHERE book_id = %s AND status = 'waiting'
          ORDER BY created_at, id LIMIT %s
        )
        """,
        (config.HOLD_READY_DAYS, book["id"], free),
    )


def book_view(conn, book: dict) -> dict:
    c = counts(conn, book["id"])
    return {
        "id": book["id"],
        "isbn": book["isbn"],
        "title": book["title"],
        "author": book["author"],
        "year": book["year"],
        "total_copies": book["total_copies"],
        "available_copies": max(book["total_copies"] - c["on_loan"] - c["ready_holds"], 0),
        "holds_waiting": c["waiting_holds"],
    }
