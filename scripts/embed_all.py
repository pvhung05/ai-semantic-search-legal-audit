"""Embed moi Khoan/Dieu ra bang chunk (GD E).

python scripts/embed_all.py [--van-ban VB_ID]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.session import ket_noi  # noqa: E402
from app.ingestion.chunks import tao_chunks_cho_van_ban  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--van-ban", default=None, help="van_ban_id cu the; mac dinh moi van ban")
    args = p.parse_args()

    with ket_noi() as conn:
        if args.van_ban:
            ids = [args.van_ban]
        else:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM van_ban ORDER BY created_at")
                ids = [r[0] for r in cur.fetchall()]
        for vb in ids:
            n = tao_chunks_cho_van_ban(conn, vb)
            conn.commit()
            print(f"{vb}: {n} chunks")


if __name__ == "__main__":
    main()
