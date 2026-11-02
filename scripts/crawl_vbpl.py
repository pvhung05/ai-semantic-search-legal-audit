"""CLI cao vbpl.vn vao Postgres schema `meta`.

Vi du:
    python scripts/crawl_vbpl.py seed-actions
    python scripts/crawl_vbpl.py seed-catalogs
    python scripts/crawl_vbpl.py discover --page 1 --page-size 20
    python scripts/crawl_vbpl.py crawl --id 66801
    python scripts/crawl_vbpl.py crawl --limit 3
    python scripts/crawl_vbpl.py stats
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.crawl_vbpl import catalogs, doc_api, pipeline, store, store_public  # noqa: E402
from app.crawl_vbpl.fetcher import Fetcher  # noqa: E402

log = logging.getLogger(__name__)


def cmd_seed_actions(args: argparse.Namespace) -> None:
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        n = store.seed_actions(conn)
        conn.commit()
    print(f"seed_actions: nap {n} action vao meta.action_config")


def cmd_seed_catalogs(args: argparse.Namespace) -> None:
    fetcher = Fetcher()
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        n = catalogs.seed_all(conn, fetcher)
    for k, v in n.items():
        print(f"seed_catalogs: {k} = {v}")


def cmd_discover(args: argparse.Namespace) -> None:
    fetcher = Fetcher()
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        for p in range(args.page, args.page + args.pages):
            pipeline.discover_from_list(conn, fetcher, page=p, page_size=args.page_size)


def cmd_crawl(args: argparse.Namespace) -> None:
    fetcher = Fetcher()
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        if args.id:
            rows = [(args.id, None)]
        else:
            rows = store.take_pending(conn, args.limit)

        print(f"Crawl {len(rows)} van ban")
        # Khi chi dinh --id, khong enqueue van ban lien quan (chi cao dung VB do)
        enqueue_related = args.id is None
        for n, (id_ref, slug) in enumerate(rows, 1):
            try:
                res = pipeline.crawl_one(conn, fetcher, id_ref, slug,
                                         enqueue_related=enqueue_related)
                store.mark_done(conn, id_ref)
                conn.commit()
                print(
                    f"[{n}/{len(rows)}] ID: {id_ref} OK | {res.so_hieu or '-':25s} | "
                    f"quan_he={res.quan_he_count} | {(res.tieu_de or '')[:60]}"
                )
            except Exception as e:
                conn.rollback()
                store.mark_error(conn, id_ref, str(e))
                conn.commit()
                log.exception("[%d/%d] %s loi: %s", n, len(rows), id_ref, e)


def cmd_build_cay(args: argparse.Namespace) -> None:
    """Nap cay (Chuong/Dieu/Khoan/Diem) tu API vao public.node + public.chunk."""
    fetcher = Fetcher()
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        if args.id:
            ids = [args.id]
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id_ref FROM meta.crawl_queue WHERE trang_thai = 'DONE' ORDER BY id_ref"
                )
                ids = [r[0] for r in cur.fetchall()]
        if args.limit:
            ids = ids[: args.limit]

        print(f"Build cay cho {len(ids)} van ban")
        tong_node = tong_chunk = 0
        for n, vb_id in enumerate(ids, 1):
            try:
                tree = doc_api.fetch_cay_noidung(fetcher, vb_id)
                res = store_public.save_cay(conn, vb_id, tree)
                conn.commit()
                tong_node += res["node"]
                tong_chunk += res["chunk"]
                print(f"[{n}/{len(ids)}] {vb_id:40s} node={res['node']:5d} chunk={res['chunk']:5d}")
            except Exception as e:
                conn.rollback()
                log.exception("[%d/%d] %s loi: %s", n, len(ids), vb_id, e)
        print(f"Tong: {tong_node} node, {tong_chunk} chunk")


def cmd_stats(args: argparse.Namespace) -> None:
    with psycopg.connect(settings.DB_URL) as conn, conn.cursor() as cur:
        print("=== Thong ke Hang doi (meta.crawl_queue) ===")
        cur.execute(
            "SELECT trang_thai, COUNT(*) FROM meta.crawl_queue GROUP BY trang_thai ORDER BY trang_thai"
        )
        for ts, n in cur.fetchall():
            print(f"queue {ts:8s} {n}")

        print("\n=== Thong ke du lieu (schema meta) ===")
        tables = (
            "documents", "document_content", "document_relations",
            "document_nganh", "document_linhvuc", "document_issues",
            "vbhn_nhom",
            "loai_vanban", "coquan_banhanh", "nganh", "linhvuc", "chucdanh",
            "relation_types",
        )
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM meta.{t}")
            print(f"{t:20s}: {cur.fetchone()[0]}")

        print("\n=== 5 van ban gan nhat trong meta.documents ===")
        cur.execute(
            """
            SELECT d.id, d.so_hieu, LEFT(d.tieu_de, 50), d.trangthai, d.ngay_hieuluc,
                   (SELECT COUNT(*) FROM meta.document_relations r 
                    WHERE r.vanban_tacdong_id = d.id OR r.vanban_bitacdong_id = d.id) AS rel_count
            FROM meta.documents d
            ORDER BY d.updated_at DESC
            LIMIT 5
            """
        )
        for row in cur.fetchall():
            print(" ", " | ".join(str(x) for x in row))


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    ap = argparse.ArgumentParser(description="Crawler vbpl.vn -> Postgres meta")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("seed-actions")
    sub.add_parser("seed-catalogs")

    d = sub.add_parser("discover")
    d.add_argument("--page", type=int, default=1)
    d.add_argument("--pages", type=int, default=1, help="So trang lien tiep tu --page")
    d.add_argument("--page-size", type=int, default=100)

    c = sub.add_parser("crawl")
    c.add_argument("--limit", type=int, default=5, help="So van ban can crawl tu queue")
    c.add_argument("--id", type=str, default=None, help="Crawl truc tiep 1 ID vbpl cu the (vd: 66801)")

    bc = sub.add_parser("build-cay")
    bc.add_argument("--id", type=str, default=None, help="Build cay 1 ID cu the")
    bc.add_argument("--limit", type=int, default=None, help="Gioi han so van ban")

    sub.add_parser("stats")

    args = ap.parse_args()
    if args.cmd == "seed-actions":
        cmd_seed_actions(args)
    elif args.cmd == "seed-catalogs":
        cmd_seed_catalogs(args)
    elif args.cmd == "discover":
        cmd_discover(args)
    elif args.cmd == "crawl":
        cmd_crawl(args)
    elif args.cmd == "build-cay":
        cmd_build_cay(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
