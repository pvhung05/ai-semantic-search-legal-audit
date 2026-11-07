"""CLI service CRAWL: cao vbpl.vn vao Postgres schema `meta`.

Service nay la noi DUY NHAT goi API vbpl.vn. No chi ghi schema `meta`; viec dung
`vanban.node` tu cay da cao thuoc service doi sanh (`python -m app.doisanh.cli build-cay`).

Vi du:
    python -m app.crawl.cli seed-actions
    python -m app.crawl.cli seed-catalogs
    python -m app.crawl.cli discover --page 1 --page-size 20
    python -m app.crawl.cli crawl --id 66801
    python -m app.crawl.cli crawl --limit 3
    python -m app.crawl.cli fetch-cay --id 66801     # luu cay tho vao vanban.document_cay
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


def _connect(autocommit: bool = False):
    """Ket noi DB co lock_timeout: neu bi ket lock > 30s -> bao loi thay vi treo vo han
    (caller bat exception, mark_error roi di tiep). Tranh crawl 'treo' khi co phien giu lock."""
    return psycopg.connect(settings.DB_URL, autocommit=autocommit,
                           options="-c lock_timeout=30000")


def cmd_seed_actions(args: argparse.Namespace) -> None:
    with _connect() as conn:
        n = store.seed_actions(conn)
        conn.commit()
    print(f"seed_actions: nap {n} action vao vanban.action_config")


def cmd_seed_catalogs(args: argparse.Namespace) -> None:
    fetcher = Fetcher()
    with _connect() as conn:
        n = catalogs.seed_all(conn, fetcher)
    for k, v in n.items():
        print(f"seed_catalogs: {k} = {v}")


def _norm_issue_dt(s: str | None) -> str | None:
    """Chuan hoa ngay cho filter vbpl: 'YYYY-MM-DD' -> 'YYYY-MM-DDT00:00:00'. Giu nguyen neu da co 'T'."""
    if not s:
        return None
    return s + "T00:00:00" if len(s) == 10 and "T" not in s else s


def cmd_discover(args: argparse.Namespace) -> None:
    fetcher = Fetcher()
    with _connect() as conn:
        dfrom = _norm_issue_dt(getattr(args, "from_date", None))
        dto = _norm_issue_dt(getattr(args, "to_date", None))
        if getattr(args, "by_year", False):
            # Chia theo nam (moi nam tu tach doi neu > tran) -> gom DU toan bo, vuot tran ~6500.
            from datetime import date
            y2 = args.to_year or date.today().year
            y1 = args.from_year
            for y in range(y2, y1 - 1, -1):
                print(f"discover nam {y} ...")
                pipeline.discover_khoang(conn, fetcher, date(y, 1, 1), date(y, 12, 31), args.page_size)
        elif getattr(args, "all", False):
            # Lap tang trang den khi het item. (Khong chia ngay -> van dinh tran ~6500 cua vbpl.)
            p = args.page
            while args.max_pages == 0 or p < args.page + args.max_pages:
                n, _ = pipeline.discover_from_list(conn, fetcher, page=p, page_size=args.page_size,
                                                   issue_from=dfrom, issue_to=dto)
                if n == 0:
                    print(f"discover: het danh sach o trang {p}")
                    break
                p += 1
            else:
                print(f"discover: dung o gioi han --max-pages ({args.max_pages})")
        else:
            for p in range(args.page, args.page + args.pages):
                pipeline.discover_from_list(conn, fetcher, page=p, page_size=args.page_size,
                                            issue_from=dfrom, issue_to=dto)


def cmd_crawl(args: argparse.Namespace) -> None:
    fetcher = Fetcher()
    with _connect() as conn:
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
    """Fetch cay noi dung (Chuong/Dieu/Khoan/Diem) tu API vbpl.vn -> vanban.document_cay."""
    fetcher = Fetcher()
    with _connect() as conn:
        if args.id:
            ids = [args.id]
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id_ref FROM vanban.crawl_queue WHERE trang_thai = 'DONE' ORDER BY id_ref"
                )
                ids = [r[0] for r in cur.fetchall()]
        if args.limit:
            ids = ids[: args.limit]

        print(f"Fetch cay cho {len(ids)} van ban -> vanban.document_cay")
        tong = 0
        for n, vb_id in enumerate(ids, 1):
            try:
                tree = doc_api.fetch_cay_noidung(fetcher, vb_id)
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO vanban.document_cay (document_id, cay, updated_at)
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
        print(f"Tong: {tong}/{len(ids)} van ban da luu cay vao vanban.document_cay")


def cmd_fetch_tac_dong(args: argparse.Namespace) -> None:
    """Fetch tac dong cap dieu khoan (diem co `type`) -> vanban.provision_impacts."""
    fetcher = Fetcher()
    with _connect() as conn:
        if args.id:
            ids = [args.id]
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id_ref FROM vanban.crawl_queue WHERE trang_thai = 'DONE' ORDER BY id_ref"
                )
                ids = [r[0] for r in cur.fetchall()]
        if args.limit:
            ids = ids[: args.limit]

        print(f"Fetch tac dong cap dieu khoan cho {len(ids)} van ban -> vanban.provision_impacts")
        tong = 0
        for n, vb_id in enumerate(ids, 1):
            try:
                impacts = doc_api.fetch_diem_tac_dong(fetcher, vb_id)
                cnt = store.save_provision_impacts(conn, vb_id, impacts)
                conn.commit()
                tong += 1
                print(f"[{n}/{len(ids)}] {vb_id:40s} {cnt} canh tac dong")
            except Exception as e:
                conn.rollback()
                log.exception("[%d/%d] %s loi: %s", n, len(ids), vb_id, e)
        print(f"Tong: {tong}/{len(ids)} van ban da luu tac dong")


def cmd_stats(args: argparse.Namespace) -> None:
    with _connect() as conn, conn.cursor() as cur:
        print("=== Thong ke Hang doi (vanban.crawl_queue) ===")
        cur.execute(
            "SELECT trang_thai, COUNT(*) FROM vanban.crawl_queue GROUP BY trang_thai ORDER BY trang_thai"
        )
        for ts, n in cur.fetchall():
            print(f"queue {ts:8s} {n}")

        print("\n=== Thong ke du lieu (vanban + danhmuc) ===")
        tables = (
            "vanban.documents", "vanban.document_content", "vanban.document_cay",
            "vanban.document_relations", "vanban.document_nganh", "vanban.document_linhvuc",
            "vanban.document_issues", "vanban.vbhn_nhom", "vanban.provision_impacts",
            "danhmuc.loai_vanban", "danhmuc.coquan_banhanh", "danhmuc.nganh",
            "danhmuc.linhvuc", "danhmuc.chucdanh", "danhmuc.relation_types",
        )
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"{t:28s}: {cur.fetchone()[0]}")

        print("\n=== 5 van ban gan nhat trong vanban.documents ===")
        cur.execute(
            """
            SELECT d.id, d.so_hieu, LEFT(d.tieu_de, 50), d.trangthai, d.ngay_hieuluc,
                   (SELECT COUNT(*) FROM vanban.document_relations r
                    WHERE r.vanban_tacdong_id = d.id OR r.vanban_bitacdong_id = d.id) AS rel_count
            FROM vanban.documents d
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
    d.add_argument("--all", action="store_true",
                   help="Don TAT CA id (TW): lap den khi het trang; bo qua --pages")
    d.add_argument("--max-pages", type=int, default=0,
                   help="Gioi han so trang khi --all (0 = khong gioi han)")
    d.add_argument("--from", dest="from_date", default=None,
                   help="Loc ngay ban hanh TU (YYYY-MM-DD; tu them T00:00:00)")
    d.add_argument("--to", dest="to_date", default=None,
                   help="Loc ngay ban hanh DEN (YYYY-MM-DD)")
    d.add_argument("--by-year", action="store_true",
                   help="Gom DU: quet tung nam, tu chia doi khoang neu > tran ~6500 (khuyen nghi)")
    d.add_argument("--from-year", type=int, default=1945, help="Nam bat dau khi --by-year")
    d.add_argument("--to-year", type=int, default=None, help="Nam ket thuc khi --by-year (mac dinh: nam nay)")

    c = sub.add_parser("crawl")
    c.add_argument("--limit", type=int, default=5, help="So van ban can crawl tu queue")
    c.add_argument("--id", type=str, default=None, help="Crawl truc tiep 1 ID vbpl cu the (vd: 66801)")

    fc = sub.add_parser("fetch-cay")
    fc.add_argument("--id", type=str, default=None, help="Fetch cay 1 ID cu the")
    fc.add_argument("--limit", type=int, default=None, help="Gioi han so van ban")

    ft = sub.add_parser("fetch-tac-dong", help="Fetch tac dong cap dieu khoan -> vanban.provision_impacts")
    ft.add_argument("--id", type=str, default=None, help="Fetch tac dong 1 ID cu the")
    ft.add_argument("--limit", type=int, default=None, help="Gioi han so van ban")

    cf = sub.add_parser("crawl-full", help="crawl metadata + fetch-cay trong 1 lenh")
    cf.add_argument("--id", type=str, nargs="+", default=None,
                    help="Mot hoac nhieu ID vbpl (cach nhau bang dau cach)")
    cf.add_argument("--limit", type=int, default=5, help="So van ban tu queue khi khong co --id")

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
    elif args.cmd == "fetch-tac-dong":
        cmd_fetch_tac_dong(args)
    elif args.cmd == "crawl-full":
        # Lap tung ID: crawl metadata + fetch cay + tac dong. Khong co --id -> theo queue 1 lan.
        for one in (args.id or [None]):
            args.id = one
            cmd_crawl(args)         # metadata + noi dung + quan he -> vanban.documents
            cmd_fetch_cay(args)     # cay phan cap -> vanban.document_cay
            cmd_fetch_tac_dong(args)  # tac dong cap dieu khoan -> vanban.provision_impacts
    elif args.cmd == "stats":
        cmd_stats(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
