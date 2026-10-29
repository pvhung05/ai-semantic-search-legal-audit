"""Pool ket noi psycopg dung chung."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.config import settings

_POOL: ConnectionPool | None = None


def _lay_pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(
            conninfo=settings.DB_URL,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": False},
            open=True,
        )
    return _POOL


@contextmanager
def ket_noi() -> Iterator[Connection]:
    """Lay mot ket noi tu pool; dong auto khi roi khoi context."""
    pool = _lay_pool()
    with pool.connection() as conn:
        yield conn


def dong_pool() -> None:
    global _POOL
    if _POOL is not None:
        _POOL.close()
        _POOL = None
