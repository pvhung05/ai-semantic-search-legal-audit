"""CLI service DOI SANH: dung kho `public` tu du lieu da cao + chay doi chieu.

Service nay KHONG goi API vbpl.vn. Lenh `build-cay` doc cay tho tu `meta.document_cay`
(do service crawl ghi qua `python -m app.crawl.cli fetch-cay`) va dung `public.node`/`public.chunk`.

Vi du:
    python -m app.doisanh.cli build-cay --id 66801
    python -m app.doisanh.cli build-cay --limit 10
"""
from __future__ import annotations

import argparse
import logging
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import psycopg

from app.core.config import settings
from app.doisanh import public_loader

log = logging.getLogger(__name__)


def cmd_build_cay(args: argparse.Namespace) -> None:
    """Dung public.node/chunk tu cay da luu o meta.document_cay (khong goi mang)."""
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        if args.id:
            ids = [args.id]
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT document_id FROM meta.document_cay ORDER BY document_id"
                )
                ids = [r[0] for r in cur.fetchall()]
        if args.limit:
            ids = ids[: args.limit]

        print(f"Build cay cho {len(ids)} van ban (nguon: meta.document_cay)")
        tong_node = tong_chunk = 0
        for n, vb_id in enumerate(ids, 1):
            try:
                res = public_loader.build_cay_tu_meta(conn, vb_id)
                conn.commit()
                tong_node += res["node"]
                tong_chunk += res["chunk"]
                print(f"[{n}/{len(ids)}] {vb_id:40s} node={res['node']:5d} chunk={res['chunk']:5d}")
            except Exception as e:
                conn.rollback()
                log.exception("[%d/%d] %s loi: %s", n, len(ids), vb_id, e)
        print(f"Tong: {tong_node} node, {tong_chunk} chunk")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    ap = argparse.ArgumentParser(description="Service doi sanh: kho public + doi chieu")
    sub = ap.add_subparsers(dest="cmd", required=True)

    bc = sub.add_parser("build-cay")
    bc.add_argument("--id", type=str, default=None, help="Build cay 1 ID cu the")
    bc.add_argument("--limit", type=int, default=None, help="Gioi han so van ban")

    args = ap.parse_args()
    if args.cmd == "build-cay":
        cmd_build_cay(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
