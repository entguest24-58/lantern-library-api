from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import config, db
from .errors import ApiError
from .routers import auth, books, fees, holds, loans
from .security import hash_password


def ensure_staff_account() -> None:
    if not (config.STAFF_EMAIL and config.STAFF_PASSWORD):
        return
    email = config.STAFF_EMAIL.lower()
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM members WHERE lower(email) = %s", (email,)).fetchone():
            return
        conn.execute(
            "INSERT INTO members (email, name, password_hash, role) VALUES (%s, %s, %s, 'staff')",
            (email, "Library staff", hash_password(config.STAFF_PASSWORD)),
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.pool.open(wait=True)
    db.apply_schema()
    ensure_staff_account()
    yield
    db.pool.close()


app = FastAPI(title="Lantern Library API", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error(_request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
    message = first.get("msg", "invalid request")
    return JSONResponse(
        status_code=400, content={"error": f"{field}: {message}" if field else message}
    )


@app.get("/health")
def health():
    with db.transaction() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


for module in (auth, books, loans, holds, fees):
    app.include_router(module.router)
