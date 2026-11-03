"""CLI service CRAWL: cao vbpl.vn vao Postgres schema `meta`.

Service nay la noi DUY NHAT goi API vbpl.vn. No chi ghi schema `meta`; viec dung
`public.node` tu cay da cao thuoc service doi sanh (`python -m app.doisanh.cli build-cay`).

Vi du:
    python -m app.crawl.cli seed-actions
    python -m app.crawl.cli seed-catalogs
    python -m app.crawl.cli discover --page 1 --page-size 20
    python -m app.crawl.cli crawl --id 66801
    python -m app.crawl.cli crawl --limit 3
    python -m app.crawl.cli fetch-cay --id 66801     # luu cay tho vao meta.document_cay
    python -m app.crawl.cli stats
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
from psycopg.types.json import Json

from app.core.config import settings
from app.crawl import catalogs, doc_api, pipeline, store
from app.crawl.fetcher import Fetcher

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


def cmd_fetch_cay(args: argparse.Namespace) -> None:
    """Fetch cay noi dung (Chuong/Dieu/Khoan/Diem) tu API vbpl.vn -> meta.document_cay."""
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

        print(f"Fetch cay cho {len(ids)} van ban -> meta.document_cay")
        tong = 0
        for n, vb_id in enumerate(ids, 1):
            try:
                tree = doc_api.fetch_cay_noidung(fetcher, vb_id)
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO meta.document_cay (document_id, cay, updated_at)
                           VALUES (%s, %s, now())
                           ON CONFLICT (document_id) DO UPDATE SET
                             cay = EXCLUDED.cay, updated_at = now()""",
                        (str(vb_id).strip(), Json(tree)),
                    )
                conn.commit()
                tong += 1
                n_node = len(tree) if isinstance(tree, list) else 0
                print(f"[{n}/{len(ids)}] {vb_id:40s} cay_goc={n_node} node")
            except Exception as e:
                conn.rollback()
                log.exception("[%d/%d] %s loi: %s", n, len(ids), vb_id, e)
        print(f"Tong: {tong}/{len(ids)} van ban da luu cay vao meta.document_cay")


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
            "documents", "document_content", "document_cay", "document_relations",
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
    ap = argparse.ArgumentParser(description="Service crawl vbpl.vn -> Postgres meta")
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

    fc = sub.add_parser("fetch-cay")
    fc.add_argument("--id", type=str, default=None, help="Fetch cay 1 ID cu the")
    fc.add_argument("--limit", type=int, default=None, help="Gioi han so van ban")

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
    elif args.cmd == "fetch-cay":
        cmd_fetch_cay(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
