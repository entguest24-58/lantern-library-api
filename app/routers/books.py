import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator

from .. import circulation
from ..db import transaction
from ..errors import bad_request, conflict, not_found
from ..security import staff_member

router = APIRouter()


def normalize_isbn(value: str) -> str:
    digits = re.sub(r"[\s-]", "", value)
    if not re.fullmatch(r"\d{9}[\dXx]|\d{13}", digits):
        raise ValueError("isbn must have 10 or 13 digits")
    return digits.upper()


class BookBody(BaseModel):
    isbn: str
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1000, le=2100)
    copies: int = Field(default=1, ge=1, le=100)

    _isbn = field_validator("isbn")(normalize_isbn)


class BookPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1000, le=2100)


class CopiesBody(BaseModel):
    count: int = Field(ge=1, le=100)


@router.get("/books")
def list_books(
    q: str | None = None,
    available: bool | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with transaction() as conn:
        params: list = []
        where = ""
        if q:
            where = "WHERE title ILIKE %s OR author ILIKE %s"
            params += [f"%{q}%", f"%{q}%"]
        books = conn.execute(
            f"SELECT * FROM books {where} ORDER BY title, id", params
        ).fetchall()
        views = [circulation.book_view(conn, b) for b in books]
    if available is not None:
        views = [v for v in views if (v["available_copies"] > 0) == available]
    return {"books": views[offset : offset + limit], "total": len(views)}


@router.get("/books/{book_id}")
def get_book(book_id: int):
    with transaction() as conn:
        book = circulation.lock_book(conn, book_id)
        if book is None:
            raise not_found("book not found")
        circulation.refresh_holds(conn, book)
        return {"book": circulation.book_view(conn, book)}


@router.post("/books", status_code=201)
def create_book(body: BookBody, _staff: dict = Depends(staff_member)):
    with transaction() as conn:
        if conn.execute("SELECT 1 FROM books WHERE isbn = %s", (body.isbn,)).fetchone():
            raise conflict("a book with this isbn already exists")
        book = conn.execute(
            "INSERT INTO books (isbn, title, author, year, total_copies) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (body.isbn, body.title.strip(), body.author.strip(), body.year, body.copies),
        ).fetchone()
        return {"book": circulation.book_view(conn, book)}


@router.patch("/books/{book_id}")
def update_book(book_id: int, body: BookPatch, _staff: dict = Depends(staff_member)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise bad_request("nothing to update")
    with transaction() as conn:
        book = circulation.lock_book(conn, book_id)
        if book is None:
            raise not_found("book not found")
        sets = ", ".join(f"{k} = %s" for k in changes)
        book = conn.execute(
            f"UPDATE books SET {sets} WHERE id = %s RETURNING *", [*changes.values(), book_id]
        ).fetchone()
        return {"book": circulation.book_view(conn, book)}


@router.post("/books/{book_id}/copies")
def add_copies(book_id: int, body: CopiesBody, _staff: dict = Depends(staff_member)):
    with transaction() as conn:
        book = circulation.lock_book(conn, book_id)
        if book is None:
            raise not_found("book not found")
        book = conn.execute(
            "UPDATE books SET total_copies = total_copies + %s WHERE id = %s RETURNING *",
            (body.count, book_id),
        ).fetchone()
        circulation.refresh_holds(conn, book)
        return {"book": circulation.book_view(conn, book)}
