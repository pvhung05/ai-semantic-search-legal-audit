"""CLI thi hanh lenh sua doi + cap nhat trang thai van ban."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ingestion.sync import dong_bo_hieu_luc  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def main() -> None:
    kq = dong_bo_hieu_luc()
    tot = sum(1 for r in kq if r.get("trang_thai") in {"ok", "da_ap_dung"})
    loi = sum(1 for r in kq if r.get("trang_thai") == "loi")
    print(f"Tong lenh: {len(kq)} | OK: {tot} | Loi: {loi}")
    for r in kq:
        if r.get("trang_thai") == "loi":
            print("  !", r)


if __name__ == "__main__":
    main()
