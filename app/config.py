import os


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


DATABASE_URL = _required("DATABASE_URL")
JWT_SECRET = _required("JWT_SECRET")
TOKEN_TTL_HOURS = 24

# Optional first staff account, created on startup when it does not exist yet.
STAFF_EMAIL = os.environ.get("STAFF_EMAIL")
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD")

LOAN_DAYS = 14
MAX_ACTIVE_LOANS = 3
MAX_ACTIVE_HOLDS = 5
HOLD_READY_DAYS = 3
LATE_FEE_CENTS_PER_DAY = 25
LATE_FEE_CAP_CENTS = 1000
BORROW_BLOCK_FEES_CENTS = 500
