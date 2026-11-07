"""Dung can cu ung vien tu ket qua hybrid (dung chung cho /audit va /ask).

Gom moi chunk top-k ve don vi KHOAN (hoac DIEU neu khong co Khoan), dung lai ca Khoan
(ten Dieu + cau dan + cac Diem con), gan Phan/Chuong + loai rang buoc + tac dong (sua doi).
"""
from __future__ import annotations

from datetime import date

from app.core.html_text import html_doc_to_text
from app.doisanh.public_loader import impacts_cho_nodes, khoi_tac_dong


def _loai_rang_buoc(text: str) -> list[str]:
    """Nhan dien loai rang buoc so lieu trong Khoan me bang keyword (rule, truoc LLM).

    - san: muc toi thieu (du thao thap hon -> vi pham)
    - tran: muc toi da / thoi han (du thao cao hon -> vi pham; thoi han dai hon -> vi pham)
    - co_dinh: con so co dinh (du thao khac -> vi pham)
    - trao_quyen: luat trao quyen tu quyet/thoa thuan (du thao chon muc cu the -> hop le)
    """
    t = (text or "").lower()
    kq: list[str] = []
    if any(k in t for k in ("ít nhất", "tối thiểu", "không thấp hơn", "không ít hơn", "không dưới")):
        kq.append("san")
    # "thoi han N ngay / cham nhat / truoc ngay" la deadline = tran (phai lam trong/truoc moc do)
    if any(k in t for k in ("không quá", "tối đa", "không vượt quá", "không được quá",
                            "không nhiều hơn", "không cao hơn",
                            "trong thời hạn", "thời hạn", "chậm nhất", "trước ngày",
                            "không được chậm")):
        kq.append("tran")
    if any(k in t for k in ("do ", "có thể thỏa thuận", "theo thỏa thuận",
                            "hai bên thỏa thuận", "tự quyết định", "do các bên")):
        kq.append("trao_quyen")
    return kq or ["khong_ro"]


def _unit_path(duong_dan: str) -> str:
    """Leo tu leaf len don vi gui LLM: Khoan neu co, nguoc lai Dieu (vd cho Dieu khong co Khoan).

    duong_dan = 'C1>D5>K2>da'; segment prefix: D=dieu, K=khoan, d=diem (xem _CAP_PREFIX).
    """
    segs = (duong_dan or "").split(">")
    for pfx in ("K", "D"):  # uu tien Khoan, roi Dieu
        for i in range(len(segs) - 1, -1, -1):
            if segs[i][:1] == pfx:
                return ">".join(segs[: i + 1])
    return duong_dan or ""


def _dieu_path(duong_dan: str) -> str | None:
    segs = (duong_dan or "").split(">")
    for i in range(len(segs) - 1, -1, -1):
        if segs[i][:1] == "D":
            return ">".join(segs[: i + 1])
    return None


def _to_tien_paths(duong_dan: str) -> list[str]:
    """Cac path to tien tich luy: 'P1>CIV>D48' -> ['P1','P1>CIV','P1>CIV>D48']."""
    segs = [s for s in (duong_dan or "").split(">") if s]
    return [">".join(segs[: i + 1]) for i in range(len(segs))]


def _phan_chuong(cur, vb_id: str, up: str) -> tuple[str | None, str | None]:
    """Nhan Phan/Chuong (kem tieu de) cua don vi, tu to tien trong cay. Vd 'Chương IV. Giải quyết tố cáo'."""
    cur.execute(
        "SELECT cap, so_thu_tu, tieu_de FROM node WHERE van_ban_id=%s AND duong_dan = ANY(%s) "
        "AND cap IN ('phan','chuong')",
        (vb_id, _to_tien_paths(up)),
    )
    d = {cap: (stt, ten) for cap, stt, ten in cur.fetchall()}

    def nhan(cap: str, nhan_cap: str) -> str | None:
        if cap not in d:
            return None
        stt, ten = d[cap]
        ten = " ".join((ten or "").split())  # gon newline/khoang trang thua trong tieu_de
        if not ten:
            return f"{nhan_cap} {stt}"
        # tieu_de thuong da co san 'Chương V ...' -> tranh lap tien to
        return ten if ten.lower().startswith(nhan_cap.lower()) else f"{nhan_cap} {stt}. {ten}"

    return nhan("phan", "Phần"), nhan("chuong", "Chương")


def nap_khoan_ung_vien(conn, chunk_ids: list[str], diem_rrf: dict[str, float]) -> list[dict]:
    """Nap can cu ung vien, GOM moi chunk top-k ve don vi KHOAN (hoac DIEU neu khong co Khoan).

    Diem/Khoan khop -> leo len Khoan me qua duong_dan; noi_dung gui LLM = "ten Dieu" +
    ca Khoan (cau dan + tat ca Diem con). Dieu khong co Khoan -> dung ca Dieu. Khu trung
    theo don vi; diem_rrf giu ban cao nhat. Moi ung vien kem Phan/Chuong, loai_rang_buoc, tac_dong.
    """
    if not chunk_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.id, n.van_ban_id, n.duong_dan FROM chunk c "
            "JOIN node n ON n.id = c.node_id WHERE c.id = ANY(%s)",
            (chunk_ids,),
        )
        leaves = cur.fetchall()

    # gom ve (van_ban, unit_path), giu rrf cao nhat
    rrf_unit: dict[tuple[str, str], float] = {}
    for cid, vb_id, duong_dan in leaves:
        key = (vb_id, _unit_path(duong_dan))
        rrf = diem_rrf.get(cid, 0.0)
        if rrf > rrf_unit.get(key, -1.0):
            rrf_unit[key] = rrf

    out: list[dict] = []
    with conn.cursor() as cur:
        for (vb_id, up), rrf in rrf_unit.items():
            dp = _dieu_path(up)
            so_dieu = ten_dieu = None
            if dp:
                cur.execute(
                    "SELECT so_thu_tu, tieu_de FROM node WHERE van_ban_id=%s AND duong_dan=%s",
                    (vb_id, dp),
                )
                if r := cur.fetchone():
                    so_dieu, ten_dieu = r
            phan, chuong = _phan_chuong(cur, vb_id, up)
            cur.execute(
                "SELECT id, cap, so_thu_tu FROM node WHERE van_ban_id=%s AND duong_dan=%s",
                (vb_id, up),
            )
            unit = cur.fetchone()
            if unit is None:
                continue
            unit_id, unit_cap, unit_stt = unit
            # ca Khoan = node don vi + toan bo con chau (Diem), theo thu tu
            cur.execute(
                "SELECT noi_dung FROM node WHERE van_ban_id=%s "
                "AND (duong_dan=%s OR duong_dan LIKE %s) ORDER BY order_index",
                (vb_id, up, up + ">%"),
            )
            than = "\n".join(
                t for t in (html_doc_to_text(r[0] or "").strip() for r in cur.fetchall()) if t
            )
            cur.execute("SELECT so_hieu, ten FROM van_ban WHERE id=%s", (vb_id,))
            vb = cur.fetchone() or (None, None)
            noi_dung = "\n".join(x for x in (ten_dieu, than) if x)
            out.append({
                "khoan_id": unit_id,
                "van_ban_id": vb_id,
                "so_hieu": vb[0] or "", "ten_van_ban": vb[1] or "",
                "so_dieu": so_dieu, "tieu_de_dieu": ten_dieu,
                "so_khoan": unit_stt if unit_cap == "khoan" else None,
                "diem": None,
                "phan": phan,
                "chuong": chuong,
                "noi_dung": noi_dung,
                "loai_rang_buoc": _loai_rang_buoc(noi_dung),
                "diem_rrf": rrf,
            })

    # Tac dong cap dieu khoan: can cu co bi sua doi/thay the/bai bo khong (ke ca mark o Dieu cha).
    # Khong chi canh bao: dua NOI DUNG SAU KHI SUA len dau can cu de LLM lay lam chuan.
    impacts = impacts_cho_nodes(conn, [u["khoan_id"] for u in out])
    ngay_iso = date.today().isoformat()
    for u in out:
        td = impacts.get(u["khoan_id"])
        if td:
            u["tac_dong"] = td
            khoi = khoi_tac_dong(td, ngay_iso)
            if khoi:
                u["noi_dung"] = khoi + "\n" + u["noi_dung"]  # prepend de khong bi cat khi [:N]
    out.sort(key=lambda x: -x["diem_rrf"])
    return out
