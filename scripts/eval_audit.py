"""Eval harness: duyet eval_case, so sanh phat hien voi loi_mong_doi, tinh recall/precision.

Cach dung:
  python scripts/eval_audit.py --save

Yeu cau: eval_case co san (tiem loi tu Dieu luat that), moi loai_loi >= 6 ca,
>= 10 mau am. Du lieu nay nguoi dung cung cap.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.doisanh.audit import mapping as mapping_mod  # noqa: E402
from app.doisanh.audit import tier1 as tier1_mod  # noqa: E402
from app.doisanh.audit import tier2 as tier2_mod  # noqa: E402
from app.doisanh.audit.segment import DonViSegment  # noqa: E402
from app.core.db.session import ket_noi  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def chay_eval(ten: str = "default") -> dict:
    with ket_noi() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, mo_ta, noi_dung_dieu, tieu_de, van_ban_me_ids, ngay_tra,
                      dieu_me_mong_doi, loi_mong_doi, linh_vuc FROM eval_case"""
        )
        cases = cur.fetchall()
    tp = fp = fn = 0
    tp_mapping = fn_mapping = 0
    chi_tiet: list[dict] = []
    for c in cases:
        cid, mo_ta, noi_dung, tieu_de, van_ban_me, ngay, dieu_mong, loi_mong, _lv = c
        dv = DonViSegment(
            id=f"EVAL-{cid}:D1", cap="dieu", so_dieu="1", tieu_de=tieu_de or "",
            noi_dung=noi_dung, hash=f"eval-{cid}", thu_tu=1,
        )
        with ket_noi() as c2:
            # tier1
            ph_t1 = tier1_mod.chay_tier1(c2, [dv], ngay or date.today(), list(van_ban_me))
            # mapping
            try:
                anh_xa = mapping_mod.anh_xa_dieu(c2, [dv], list(van_ban_me), ngay or date.today())
                dieu_me_ids = [d for ax in anh_xa for d in (ax.get("dieu_me_ids") or [])]
                tp_mapping += len(set(dieu_me_ids) & set(dieu_mong or []))
                fn_mapping += len(set(dieu_mong or []) - set(dieu_me_ids))
            except Exception as exc:
                logging.warning("mapping loi case %s: %s", cid, exc)
                dieu_me_ids = []
            # tier2
            try:
                ph_t2 = tier2_mod.chay_tier2_cho_dieu(
                    c2, dv, [dv], dieu_me_ids[:6], ngay or date.today(), None,
                )
            except Exception as exc:
                logging.warning("tier2 loi case %s: %s", cid, exc)
                ph_t2 = []
        loai_hien = {p.loai_loi for p in ph_t1} | {p.loai_loi for p in ph_t2}
        loai_mong = {x["loai_loi"] for x in (loi_mong or [])}
        tp += len(loai_hien & loai_mong)
        fp += len(loai_hien - loai_mong)
        fn += len(loai_mong - loai_hien)
        chi_tiet.append({"case_id": cid, "mong": sorted(loai_mong), "thuc": sorted(loai_hien)})

    recall = tp / max(1, tp + fn)
    precision = tp / max(1, tp + fp)
    rec_map = tp_mapping / max(1, tp_mapping + fn_mapping)
    ket_qua = {
        "so_case": len(cases),
        "tp": tp, "fp": fp, "fn": fn,
        "recall": recall, "precision": precision,
        "mapping_recall": rec_map,
        "chi_tiet": chi_tiet[:10],
    }
    return ket_qua


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--save", action="store_true")
    p.add_argument("--ten", default="default")
    args = p.parse_args()
    kq = chay_eval(args.ten)
    print(json.dumps(kq, ensure_ascii=False, indent=2))
    if args.save:
        with ket_noi() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO eval_run (ten, cau_hinh, ket_qua) VALUES (%s,%s,%s)",
                (args.ten, json.dumps({}), json.dumps(kq)),
            )
            conn.commit()
