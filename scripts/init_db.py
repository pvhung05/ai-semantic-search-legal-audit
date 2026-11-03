"""Ap dung migrations/*.sql tuan tu, ghi nhan vao bang schema_migrations.

Chay lai idempotent: migration da co trong schema_migrations se bo qua.
Moi file SQL duoc chay trong mot transaction rieng.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"

sys.path.insert(0, str(ROOT))
from app.core.config import settings  # noqa: E402


def _da_chay(cur: psycopg.Cursor, ten: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_migrations'"
    )
    if cur.fetchone() is None:
        return False
    cur.execute("SELECT 1 FROM schema_migrations WHERE ten = %s", (ten,))
    return cur.fetchone() is not None


def _ghi_nhan(cur: psycopg.Cursor, ten: str) -> None:
    cur.execute(
        "INSERT INTO schema_migrations(ten) VALUES (%s) ON CONFLICT DO NOTHING",
        (ten,),
    )


def ap_dung_migrations(db_url: str, migrations_dir: Path = MIGRATIONS_DIR) -> None:
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        print(f"[init_db] khong tim thay file .sql trong {migrations_dir}")
        return

    with psycopg.connect(db_url, autocommit=False) as conn:
        for sql_file in files:
            ten = sql_file.name
            with conn.cursor() as cur:
                if _da_chay(cur, ten):
                    print(f"[init_db] bo qua {ten} (da chay)")
                    continue
                print(f"[init_db] ap dung {ten}")
                cur.execute(sql_file.read_text(encoding="utf-8"))
                _ghi_nhan(cur, ten)
            conn.commit()
    print("[init_db] xong")


if __name__ == "__main__":
    ap_dung_migrations(settings.DB_URL)
