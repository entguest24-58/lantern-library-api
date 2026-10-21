from fastapi import APIRouter, Depends

from ..db import transaction
from ..errors import conflict, forbidden, not_found
from ..security import current_member, staff_member

router = APIRouter()


@router.get("/fees")
def list_fees(member_id: int | None = None, member: dict = Depends(current_member)):
    if member_id is not None and member_id != member["id"] and member["role"] != "staff":
        raise forbidden()
    target = member_id if member_id is not None else member["id"]
    with transaction() as conn:
        fees = conn.execute(
            "SELECT id, loan_id, amount_cents, created_at, paid_at FROM fees "
            "WHERE member_id = %s ORDER BY created_at DESC, id DESC",
            (target,),
        ).fetchall()
    unpaid = sum(f["amount_cents"] for f in fees if f["paid_at"] is None)
    return {"fees": fees, "unpaid_cents": unpaid}


@router.post("/fees/{fee_id}/pay")
def pay_fee(fee_id: int, _staff: dict = Depends(staff_member)):
    with transaction() as conn:
        fee = conn.execute("SELECT * FROM fees WHERE id = %s FOR UPDATE", (fee_id,)).fetchone()
        if fee is None:
            raise not_found("fee not found")
        if fee["paid_at"] is not None:
            raise conflict("fee already paid")
        fee = conn.execute(
            "UPDATE fees SET paid_at = now() WHERE id = %s "
            "RETURNING id, loan_id, amount_cents, created_at, paid_at",
            (fee_id,),
        ).fetchone()
    return {"fee": fee}
