from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Request

from . import config
from .db import transaction
from .errors import forbidden, unauthorized


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def issue_token(member: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(member["id"]),
        "role": member["role"],
        "iat": now,
        "exp": now + timedelta(hours=config.TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def current_member(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized()
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise unauthorized("invalid or expired token")
    with transaction() as conn:
        member = conn.execute(
            "SELECT id, email, name, role, created_at FROM members WHERE id = %s",
            (int(payload["sub"]),),
        ).fetchone()
    if member is None:
        raise unauthorized("invalid or expired token")
    return member


def staff_member(member: dict = Depends(current_member)) -> dict:
    if member["role"] != "staff":
        raise forbidden()
    return member
