from contextlib import contextmanager
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

pool = ConnectionPool(
    config.DATABASE_URL, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@contextmanager
def transaction():
    """One connection, one transaction: commits on success, rolls back on error."""
    with pool.connection() as conn:
        with conn.transaction():
            yield conn


def apply_schema() -> None:
    with transaction() as conn:
        conn.execute(SCHEMA_PATH.read_text())
