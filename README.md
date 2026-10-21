# Lantern Library API

REST API for the Lantern community library: member accounts, the book catalog, loans, holds and late fees.
Python 3.12, FastAPI and PostgreSQL. Money values are integer cents.

## Running

| Variable         | Required | Default | Purpose                                              |
| ---------------- | -------- | ------- | ---------------------------------------------------- |
| `DATABASE_URL`   | yes      |         | PostgreSQL connection string (`postgresql://…`)      |
| `JWT_SECRET`     | yes      |         | Secret used to sign access tokens                    |
| `PORT`           | no       | `8000`  | HTTP port (Docker image)                             |
| `STAFF_EMAIL`    | no       |         | With `STAFF_PASSWORD`, creates a staff account on startup if missing |
| `STAFF_PASSWORD` | no       |         | Password for that staff account                      |

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=postgresql://user:pass@localhost:5432/lantern JWT_SECRET=change-me uvicorn app.main:app --reload
```

On startup the server applies `db/schema.sql` (idempotent).

Docker: `docker build -t lantern-library-api .` then run it with the same environment variables (listens on 8000).

Staff accounts cannot be created through the API; use `STAFF_EMAIL`/`STAFF_PASSWORD` or insert a row with
role `staff` and a bcrypt password hash.

## Conventions

- Authenticated requests send `Authorization: Bearer <token>`. Tokens expire after 24 hours.
- Errors are JSON `{ "error": "<message>" }`: 400 validation, 401 missing/invalid token or bad credentials,
  403 staff only, 404 not found (including another member's loan or hold), 409 a circulation rule blocks the request.

## Endpoints

| Method | Path                     | Auth   | Notes |
| ------ | ------------------------ | ------ | ----- |
| GET    | `/health`                | -      | Database reachable |
| POST   | `/auth/register`         | -      | `{ email, name, password }`, password 8+ chars, email unique (case-insensitive). 201 `{ member }` |
| POST   | `/auth/login`            | -      | `{ email, password }` → `{ token, member }` |
| GET    | `/me`                    | member | `{ member }` |
| GET    | `/books`                 | -      | `?q=` title/author search, `?available=true|false`, `limit` (≤100), `offset` → `{ books, total }` |
| GET    | `/books/{id}`            | -      | `{ book }` with `available_copies` and `holds_waiting` |
| POST   | `/books`                 | staff  | `{ isbn, title, author, year?, copies? }`; ISBN 10 or 13 digits (hyphens ignored), unique |
| PATCH  | `/books/{id}`            | staff  | `{ title?, author?, year? }` |
| POST   | `/books/{id}/copies`     | staff  | `{ count }` adds copies; waiting holds get them first |
| POST   | `/loans`                 | member | `{ book_id }` 201 `{ loan }`, due in 14 days |
| GET    | `/loans`                 | member | Own loans; staff may pass `?member_id=` |
| POST   | `/loans/{id}/renew`      | member | Borrower only; +14 days |
| POST   | `/loans/{id}/return`     | member | Borrower or staff → `{ loan, fee }` |
| POST   | `/holds`                 | member | `{ book_id }` 201 `{ hold }` with queue `position` |
| GET    | `/holds`                 | member | Own holds |
| DELETE | `/holds/{id}`            | member | Cancel own waiting/ready hold |
| GET    | `/fees`                  | member | `{ fees, unpaid_cents }`; staff may pass `?member_id=` |
| POST   | `/fees/{id}/pay`         | staff  | Mark a fee paid |

## Circulation rules

- A member may have at most 3 active loans and cannot borrow while unpaid fees total 500 cents or more.
- A member cannot borrow a book they already have on loan.
- Copies set aside for a ready hold are not available to other members.
- A loan can be renewed once, not when overdue and not while another member is waiting for the book.
- Returning late adds a fee of 25 cents per started day late, capped at 1000 cents.
- Holds can only be placed when no copy is available, one per member per book, at most 5 active per member,
  and not for a book the member has on loan. When a copy frees up, the earliest waiting hold becomes `ready`
  for 3 days; borrowing the book fulfils it, otherwise it expires and the next member is offered the copy.
