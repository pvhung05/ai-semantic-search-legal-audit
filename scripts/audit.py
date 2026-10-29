"""CLI chay doi chieu mot du thao.

python scripts/audit.py --file du_thao.docx --loai du_thao_thong_tu \
    --ngay 2026-06-01 --auto
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.audit.report import tao_report_md  # noqa: E402
from app.audit.workflow import tao_phien_tu_du_thao, tiep_tuc  # noqa: E402
from app.db.session import ket_noi  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--loai", required=True, help="du_thao_thong_tu|du_thao_nghi_dinh|...")
    p.add_argument("--ngay", required=True, help="YYYY-MM-DD")
    p.add_argument("--linh-vuc", nargs="*", default=[])
    p.add_argument("--cap-tuong-duong", type=int, default=None)
    p.add_argument("--auto", action="store_true", help="tu dong duyet moi buoc")
    p.add_argument("--che-do", default="cay", choices=["cay", "truy_hoi", "ket_hop"])
    p.add_argument("--out", type=Path, default=Path("report.md"))
    args = p.parse_args()

    ngay = date.fromisoformat(args.ngay)
    phien_id = tao_phien_tu_du_thao(
        args.file, args.loai, ngay,
        linh_vuc=args.linh_vuc, cap_tuong_duong=args.cap_tuong_duong,
        tu_dong_duyet=args.auto, che_do=args.che_do,
    )
    print(f"Phien: {phien_id}")
    while True:
        kq = tiep_tuc(phien_id)
        print(kq)
        if kq.get("buoc") in {"xong", "loi"}:
            break
        if not args.auto:
            break
        if "ghi_chu" in kq and "duyet" in kq["ghi_chu"]:
            break
    with ket_noi() as conn:
        args.out.write_text(tao_report_md(conn, phien_id), encoding="utf-8")
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
