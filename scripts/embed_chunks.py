"""Sinh embedding cho rag.chunk tu cot text_embed (model EMBED_MODEL, bge-m3 1024d).

Chi xu ly chunk co embedding IS NULL -> chay lai idempotent. Khong goi vbpl.vn,
chi goi EMBED_URL. Logic chung o public_loader.nhung_chunk_thieu (dung lai boi `build-cay --embed`).

Vi du:
    python scripts/embed_chunks.py               # tat ca chunk chua co embedding
    python scripts/embed_chunks.py --id 174877   # chi 1 van ban
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from app.core.config import settings
from app.doisanh.public_loader import nhung_chunk_thieu

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh embedding cho rag.chunk tu text_embed")
    ap.add_argument("--id", type=str, default=None, help="Chi xu ly 1 van_ban_id")
    ap.add_argument("--batch", type=int, default=settings.EMBED_BATCH_SIZE)
    args = ap.parse_args()

    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        so = nhung_chunk_thieu(conn, van_ban_id=args.id, batch_size=args.batch)
    print(f"Xong: {so} chunk da co embedding (model={settings.EMBED_MODEL}, dim={settings.EMBED_DIM})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
