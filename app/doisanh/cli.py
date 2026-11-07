"""CLI service DOI SANH: dung kho `public` tu du lieu da cao + chay doi chieu.

Service nay KHONG goi API vbpl.vn. Lenh `build-cay` doc cay tho tu `vanban.document_cay`
(do service crawl ghi qua `python -m app.crawl.cli fetch-cay`) va dung `vanban.node`/`rag.chunk`.

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
    """Dung vanban.node/chunk tu cay da luu o vanban.document_cay (khong goi mang)."""
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        if args.id:
            ids = [args.id]
        else:
            # Mac dinh chi build cac van ban CHUA build (da_build=false). --rebuild -> lam lai het.
            where = "" if getattr(args, "rebuild", False) else " WHERE da_build = false"
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT document_id FROM vanban.document_cay{where} ORDER BY document_id"
                )
                ids = [r[0] for r in cur.fetchall()]
        if args.limit:
            ids = ids[: args.limit]

        print(f"Build cay cho {len(ids)} van ban (nguon: vanban.document_cay)")
        tong_node = tong_chunk = tong_emb = 0
        for n, vb_id in enumerate(ids, 1):
            try:
                res = public_loader.build_cay_tu_meta(conn, vb_id)
                conn.commit()
                tong_node += res["node"]
                tong_chunk += res["chunk"]
                emb_txt = ""
                if args.embed:
                    so_emb = public_loader.nhung_chunk_thieu(conn, van_ban_id=vb_id)
                    tong_emb += so_emb
                    emb_txt = f" embed={so_emb:5d}"
                # port tac dong cap dieu khoan (neu da co trong vanban.provision_impacts)
                td = public_loader.port_impacts(conn, vb_id)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE vanban.document_cay SET da_build = true WHERE document_id = %s",
                        (vb_id,),
                    )
                conn.commit()
                print(f"[{n}/{len(ids)}] {vb_id:40s} node={res['node']:5d} chunk={res['chunk']:5d}"
                      f"{emb_txt} tac_dong={td['tac_dong']:4d}")
            except Exception as e:
                conn.rollback()
                log.exception("[%d/%d] %s loi: %s", n, len(ids), vb_id, e)
        msg = f"Tong: {tong_node} node, {tong_chunk} chunk"
        if args.embed:
            msg += f", {tong_emb} embedding"
        print(msg)


def cmd_port_impacts(args: argparse.Namespace) -> None:
    """Port vanban.provision_impacts -> vanban.tac_dong (khong goi mang)."""
    with psycopg.connect(settings.DB_URL, autocommit=False) as conn:
        if args.id:
            ids = [args.id]
        else:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT target_doc_id FROM vanban.provision_impacts ORDER BY 1")
                ids = [r[0] for r in cur.fetchall()]
        if args.limit:
            ids = ids[: args.limit]

        tong = 0
        for n, vb_id in enumerate(ids, 1):
            try:
                res = public_loader.port_impacts(conn, vb_id)
                conn.commit()
                tong += res["tac_dong"]
                print(f"[{n}/{len(ids)}] {vb_id:40s} tac_dong={res['tac_dong']:4d} bo_qua={res['bo_qua']:4d}")
            except Exception as e:
                conn.rollback()
                log.exception("[%d/%d] %s loi: %s", n, len(ids), vb_id, e)
        print(f"Tong: {tong} tac_dong")


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
    bc.add_argument("--rebuild", action="store_true",
                    help="Build lai ca van ban da_build=true (mac dinh chi build cai chua build)")
    bc.add_argument("--embed", action="store_true",
                    help="Sinh luon embedding cho chunk vua dung (tu text_embed)")

    pi = sub.add_parser("port-impacts", help="Port vanban.provision_impacts -> vanban.tac_dong")
    pi.add_argument("--id", type=str, default=None, help="Port 1 ID cu the")
    pi.add_argument("--limit", type=int, default=None, help="Gioi han so van ban")

    args = ap.parse_args()
    if args.cmd == "build-cay":
        cmd_build_cay(args)
    elif args.cmd == "port-impacts":
        cmd_port_impacts(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
