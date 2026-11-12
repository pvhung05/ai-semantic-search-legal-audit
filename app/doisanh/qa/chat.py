"""Hoi-dap kieu RAG: hybrid search -> dung can cu GIONG /audit -> LLM tra loi co trich dan.

Luong:
1. Embed cau hoi + hybrid search (vector + BM25) qua tim_hybrid_tu_text.
2. Gom ket qua ve Khoan me qua nap_khoan_ung_vien (ca Khoan + Phan/Chuong + tac dong) - chung voi /audit.
3. Dong goi vao prompt, yeu cau LLM tra loi va chi ra chi muc [1], [2]...
4. Tra ve {tra_loi, can_cu: [{so_hieu, phan, chuong, so_dieu, khoan, trich_dan, da_sua, ...}]}.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from psycopg import Connection

from app.core.config import settings
from app.core.models.llm import goi_chat
from app.doisanh.public_loader import tac_dong_tom_tat
from app.doisanh.retrieval.can_cu import nap_khoan_ung_vien
from app.doisanh.retrieval.hybrid import tim_hybrid_tu_text

logger = logging.getLogger(__name__)


def _vi_tri(u: dict) -> str:
    """Vi tri can cu: 'Phan.. Chuong.. Dieu X khoan Y' tu ung vien (giong /audit)."""
    parts = []
    for k in ("phan", "chuong"):
        if u.get(k):
            parts.append(u[k])
    if u.get("so_dieu"):
        parts.append(f"Điều {u['so_dieu']}")
    if u.get("so_khoan"):
        parts.append(f"khoản {u['so_khoan']}")
    if u.get("diem"):
        parts.append(f"điểm {u['diem']}")
    return " ".join(parts) or (u.get("so_hieu") or "")


def _dinh_dang_can_cu(ung_vien: list[dict], max_char: int = 1200) -> str:
    """Dong goi can cu cho prompt. noi_dung da co khoi 'noi dung sau khi sua' o dau (neu bi tac dong)."""
    khoi = []
    for i, u in enumerate(ung_vien, 1):
        vi_tri = u.get("so_hieu", "")
        chi_tiet = _vi_tri(u)
        tieu = f"{vi_tri} — {chi_tiet}" if chi_tiet else vi_tri
        khoi.append(f"[{i}] {tieu}\n{(u.get('noi_dung') or '')[:max_char]}")
    return "\n\n".join(khoi)


SYSTEM_PROMPT = """Bạn là trợ lý pháp luật Việt Nam. Trả lời CÂU HỎI của người dùng bằng tiếng Việt, tự nhiên, dễ hiểu, CHỈ dựa trên các CĂN CỨ được cung cấp.

NGUYÊN TẮC TRẢ LỜI
1. Mở đầu bằng kết luận trực tiếp (ví dụ: "Có…", "Không…", "Không có cơ quan nào được phép…"), sau đó mới giải thích. Có thể dùng gạch đầu dòng hoặc ví dụ nếu giúp dễ hiểu.
2. Mỗi ý khẳng định phải dẫn chiếu căn cứ theo số thứ tự, ví dụ "... theo [2]". Chỉ dẫn chiếu khi căn cứ đó NÓI ĐÚNG ý đó. Nếu không có căn cứ nào nói ý đó thì không đưa ý đó vào câu trả lời.
3. Không bịa nội dung luật. Không tự thêm ngoại lệ, điều kiện hay "trường hợp cần thiết" mà căn cứ không ghi.
4. Bỏ qua các căn cứ không liên quan đến câu hỏi; không trích dẫn chúng cho đủ số lượng.

KIỂM TRA TIỀN ĐỀ CỦA CÂU HỎI
5. Câu hỏi có thể chứa giả định sai (ví dụ hỏi "cơ quan nào được phép…" trong khi pháp luật nghiêm cấm việc đó). Nếu căn cứ cho thấy giả định sai, phải nói rõ ngay ở câu đầu tiên. "Không", "không có", "pháp luật nghiêm cấm" là câu trả lời hợp lệ.
6. Không suy ra một cơ quan, cá nhân "được phép" làm việc gì chỉ vì căn cứ không cấm. Quyền hạn của cơ quan nhà nước phải có quy định cho phép rõ ràng.

PHÂN BIỆT KHÁI NIỆM
7. Phân biệt rõ các chế định gần giống nhau: khiếu nại – tố cáo – kiến nghị, phản ánh; người khiếu nại – người tố cáo; người bị khiếu nại – người bị tố cáo; giải quyết lần đầu – lần hai. Không áp quy định của chế định này sang chế định khác.

KHI THIẾU CĂN CỨ
8. Nếu căn cứ không đủ để trả lời chắc chắn, nói thẳng là chưa đủ cơ sở và nêu cụ thể còn thiếu quy định về vấn đề gì, thay vì đoán.

HIỆU LỰC VĂN BẢN
9. Nếu một căn cứ mở đầu bằng khối '[CAN CU NAY ... DUNG NOI DUNG SAU KHI SUA LAM CHUAN]' kèm dòng 'Noi dung sau khi sua: ...' thì PHẢI trả lời theo nội dung sau khi sửa, và nói rõ căn cứ đó đã được sửa đổi bởi văn bản, điều khoản nào (ghi trong khối).
10. Nếu khối ghi 'DA HET HIEU LUC' thì căn cứ đó không còn hiệu lực: không dùng làm cơ sở kết luận và phải cảnh báo người dùng.

TỰ KIỂM TRA TRƯỚC KHI TRẢ LỜI
11. Kiểm tra lại: (a) mọi ý đều có căn cứ thật sự nói ý đó; (b) không có câu nào mâu thuẫn với câu khác (ví dụ vừa nói "được cung cấp thông tin" vừa nói "phải giữ bí mật thông tin"); (c) kết luận ở câu đầu khớp với phần giải thích.
"""

def hoi_dap(
    conn: Connection, cau_hoi: str,
    top_k: int = 8, ngay: date | None = None,
    van_ban_ids: list[str] | None = None, linh_vuc: list[str] | None = None,
    cap_max: int | None = None, nguong_rrf: float = 0.0,
    is_local: bool | None = None,
    think: bool | None = None,
    lich_su: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Tra ve {tra_loi, can_cu, so_can_cu}. Rong neu khong tim thay chunk nao."""
    cau_hoi = cau_hoi.strip()
    if not cau_hoi:
        return {"tra_loi": "", "can_cu": [], "so_can_cu": 0}
    rong = {
        "tra_loi": "Toi khong tim thay can cu phap ly phu hop trong kho du lieu.",
        "can_cu": [], "so_can_cu": 0,
    }
    rows = tim_hybrid_tu_text(
        conn, cau_hoi, ngay=ngay, cap_max=cap_max,
        van_ban_ids=van_ban_ids, linh_vuc=linh_vuc,
        nguong=nguong_rrf, top_k=settings.RERANK_LAY_VE,
    )
    if not rows:
        return rong
    # Dung can cu GIONG /audit: gom ve Khoan me -> rerank xuong RERANK_TOP_N.
    diem_rrf = {r["chunk_id"]: r["diem_rrf"] for r in rows}
    ung_vien = nap_khoan_ung_vien(
        conn, [r["chunk_id"] for r in rows], diem_rrf,
        query=cau_hoi, top_n=settings.RERANK_TOP_N,
    )
    if not ung_vien:
        return rong

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Nho hoi-dap truoc do (chi VAN BAN, khong kem can cu) -> giu mach hoi tiep.
    if lich_su and settings.HISTORY_CHAT > 0:
        for luot in lich_su[-settings.HISTORY_CHAT:]:
            hoi, dap = (luot.get("hoi") or "").strip(), (luot.get("dap") or "").strip()
            if hoi:
                messages.append({"role": "user", "content": hoi})
            if dap:
                messages.append({"role": "assistant", "content": dap})
    messages.append({"role": "user", "content": (
        f"CAU HOI: {cau_hoi}\n\n"
        f"CAC CAN CU PHAP LY (top-{len(ung_vien)} khoan lien quan):\n"
        f"{_dinh_dang_can_cu(ung_vien)}\n\n"
        "Hay tra loi CAU HOI mot cach tu nhien, de hieu, moi y co dan chieu [so] can cu "
        "tuong ung. Neu cau hoi la hoi tiep (vd 'the con...', 'truong hop do thi sao'), "
        "hieu theo ngu canh cac luot truoc."
    )})
    tra_loi = goi_chat(messages, is_local=is_local, think=think)  # temperature theo settings.LLM_TEMPERATURE (.env)
    ngay_iso = (ngay or date.today()).isoformat()
    return {
        "tra_loi": tra_loi.strip(),
        "can_cu": [
            {
                "so_tt": i, "van_ban_id": u["van_ban_id"], "so_hieu": u["so_hieu"],
                "ten_van_ban": u["ten_van_ban"],
                "phan": u.get("phan"), "chuong": u.get("chuong"),
                "so_dieu": u["so_dieu"], "so_khoan": u["so_khoan"], "diem": u["diem"],
                "trich_dan": u["noi_dung"], "diem_rrf": round(u["diem_rrf"], 4),
                "da_sua": tac_dong_tom_tat(u.get("tac_dong"), ngay_iso) if u.get("tac_dong") else None,
            }
            for i, u in enumerate(ung_vien, 1)
        ],
        "so_can_cu": len(ung_vien),
    }
