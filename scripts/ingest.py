"""CLI nap mot van ban luat vao DB.

Vi du:
  python scripts/ingest.py --file data/raw/blld2019.pdf \
      --id BLLD-2019-45 --so-hieu 45/2019/QH14 \
      --ten "Bo luat Lao dong" --loai bo_luat --cap 2 \
      --linh-vuc lao_dong --ngay-ban-hanh 2019-11-20 \
      --ngay-hieu-luc 2021-01-01
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.doisanh.ingestion.pipeline import nap_van_ban  # noqa: E402
from app.core.models.schemas import VanBanMeta  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def _ngay(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--id", required=True, help="van_ban.id, vd BLLD-2019-45")
    p.add_argument("--so-hieu", required=True)
    p.add_argument("--ten", required=True)
    p.add_argument("--loai", required=True, help="hien_phap|bo_luat|luat|nghi_quyet|nghi_dinh|quyet_dinh|thong_tu|khac")
    p.add_argument("--cap", type=int, required=True)
    p.add_argument("--co-quan", default=None)
    p.add_argument("--ngay-ban-hanh", default=None)
    p.add_argument("--ngay-hieu-luc", default=None)
    p.add_argument("--ngay-het-hieu-luc", default=None)
    p.add_argument("--linh-vuc", nargs="*", default=[])
    p.add_argument("--la-sua-doi", action="store_true", help="danh dau la van ban sua doi")
    p.add_argument("--tin-cay", default="can_ra_soat", choices=["xac_nhan", "can_ra_soat"])
    p.add_argument("--khong-tom-tat", action="store_true")
    args = p.parse_args()

    meta = VanBanMeta(
        id=args.id,
        so_hieu=args.so_hieu,
        ten=args.ten,
        loai=args.loai,
        cap=args.cap,
        co_quan_ban_hanh=args.co_quan,
        ngay_ban_hanh=_ngay(args.ngay_ban_hanh),
        ngay_hieu_luc=_ngay(args.ngay_hieu_luc),
        ngay_het_hieu_luc=_ngay(args.ngay_het_hieu_luc),
        linh_vuc=list(args.linh_vuc),
        la_van_ban_sua_doi=args.la_sua_doi,
        tin_cay=args.tin_cay,
    )
    ket_qua = nap_van_ban(
        args.file, meta,
        hieu_luc_tu=meta.ngay_hieu_luc,
        chay_tom_tat=not args.khong_tom_tat,
    )
    print(ket_qua)


if __name__ == "__main__":
    main()
