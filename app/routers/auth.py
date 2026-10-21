from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from ..db import transaction
from ..errors import conflict, unauthorized
from ..security import check_password, current_member, hash_password, issue_token

router = APIRouter()


class RegisterBody(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


def member_view(m: dict) -> dict:
    return {"id": m["id"], "email": m["email"], "name": m["name"], "role": m["role"]}


@router.post("/auth/register", status_code=201)
def register(body: RegisterBody):
    email = body.email.lower()
    with transaction() as conn:
        exists = conn.execute(
            "SELECT 1 FROM members WHERE lower(email) = %s", (email,)
        ).fetchone()
        if exists:
            raise conflict("email already registered")
        member = conn.execute(
            "INSERT INTO members (email, name, password_hash) VALUES (%s, %s, %s) RETURNING *",
            (email, body.name.strip(), hash_password(body.password)),
        ).fetchone()
    return {"member": member_view(member)}


@router.post("/auth/login")
def login(body: LoginBody):
    with transaction() as conn:
        member = conn.execute(
            "SELECT * FROM members WHERE lower(email) = %s", (body.email.lower(),)
        ).fetchone()
    if member is None or not check_password(body.password, member["password_hash"]):
        raise unauthorized("invalid email or password")
    return {"token": issue_token(member), "member": member_view(member)}


@router.get("/me")
def me(member: dict = Depends(current_member)):
    return {"member": member_view(member)}
