"""Soi pipeline retrieval: 1 cau -> 40 chunk hybrid -> can cu sau rerank gui LLM.

Dung CHINH cac ham cua /ask (tim_hybrid_tu_text + nap_khoan_ung_vien) de ket qua
giong het luong that. Can DB + EMBED_URL (+ RERANK_URL neu muon rerank that; khong
co thi rerank fallback giu thu tu hybrid).

Chay:
    python tests/debug_retrieval.py "nguoi khieu nai co quyen gi"
    python tests/debug_retrieval.py "..." --top-k 40 --top-n 8
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # cho phep chay truc tiep

from app.core.config import settings
from app.core.db.session import ket_noi
from app.doisanh.retrieval.can_cu import nap_khoan_ung_vien
from app.doisanh.retrieval.hybrid import tim_hybrid_tu_text


def _vi_tri(u: dict) -> str:
    return " ".join(filter(None, [
        u.get("phan"), u.get("chuong"),
        f"Điều {u['so_dieu']}" if u.get("so_dieu") else None,
        f"khoản {u['so_khoan']}" if u.get("so_khoan") else None,
        f"điểm {u['diem']}" if u.get("diem") else None,
    ]))


def soi(cau: str, top_k: int, top_n: int, out: Path) -> None:
    with ket_noi() as conn:
        rows = tim_hybrid_tu_text(conn, cau, top_k=top_k)
        if not rows:
            print("Khong tim thay chunk nao."); return

        ids = [r["chunk_id"] for r in rows]
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.text_embed, n.duong_dan, v.so_hieu "
                "FROM chunk c JOIN node n ON n.id = c.node_id "
                "JOIN van_ban v ON v.id = n.van_ban_id WHERE c.id = ANY(%s)",
                (ids,),
            )
            meta = {cid: (te, dd, sh) for cid, te, dd, sh in cur.fetchall()}

        diem_rrf = {r["chunk_id"]: r["diem_rrf"] for r in rows}
        ung_vien = nap_khoan_ung_vien(conn, ids, diem_rrf, query=cau, top_n=top_n)

    rerank_bat = "có" if settings.RERANK_URL else "không (fallback giữ thứ tự hybrid)"
    md: list[str] = [
        f"# Soi retrieval — \"{cau}\"",
        f"_Tạo lúc {datetime.now():%Y-%m-%d %H:%M:%S}_  ",
        f"top_k={top_k} · top_n={top_n} · rerank: {rerank_bat}",
        "",
        f"## 1) Retrieval hybrid — {len(rows)} chunk",
        "",
    ]
    for i, r in enumerate(rows, 1):
        te, dd, sh = meta.get(r["chunk_id"], ("", "", ""))
        md += [f"### [{i}] rrf={r['diem_rrf']:.4f} — {sh} — `{dd}`", "", (te or "").strip(), ""]

    md += ["", f"## 2) Sau rerank → đưa lên LLM — {len(ung_vien)} căn cứ", ""]
    for i, u in enumerate(ung_vien, 1):
        md += [f"### [{i}] rrf={u['diem_rrf']:.4f} — {u['so_hieu']} — {_vi_tri(u)}",
               "", (u["noi_dung"] or "").strip(), ""]

    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Hybrid: {len(rows)} chunk · sau rerank → LLM: {len(ung_vien)} căn cứ")
    print(f"Đã ghi báo cáo đầy đủ: {out.resolve()}")


def main() -> None:
    p = argparse.ArgumentParser(description="Soi retrieval + rerank cho 1 cau hoi, xuat file .md")
    p.add_argument("cau", help="Cau hoi / cau can tra cuu")
    p.add_argument("--top-k", type=int, default=40, help="So chunk hybrid lay ve (mac dinh 40)")
    p.add_argument("--top-n", type=int, default=settings.RERANK_TOP_N,
                   help="So can cu sau rerank gui LLM (mac dinh theo .env RERANK_TOP_N)")
    p.add_argument("--out", type=Path, default=Path("debug_retrieval.md"),
                   help="Duong dan file .md xuat ra (mac dinh ./debug_retrieval.md)")
    a = p.parse_args()
    if not a.cau.strip():
        print("Cau rong."); sys.exit(1)
    soi(a.cau.strip(), a.top_k, a.top_n, a.out)


if __name__ == "__main__":
    main()
