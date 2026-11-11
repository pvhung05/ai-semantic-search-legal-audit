"""Dung can cu ung vien tu ket qua hybrid (dung chung cho /audit va /ask).

Gom moi chunk top-k ve don vi KHOAN (hoac DIEU neu khong co Khoan), dung lai ca Khoan
(ten Dieu + cau dan + cac Diem con), gan Phan/Chuong + loai rang buoc + tac dong (sua doi).
"""
from __future__ import annotations

from datetime import date

from app.core.html_text import html_doc_to_text
from app.doisanh.public_loader import impacts_cho_nodes, khoi_tac_dong
from app.doisanh.retrieval.rerank import rerank


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
    if any(k in t for k in (
        "có thể thỏa thuận", "theo thỏa thuận", "hai bên thỏa thuận", "các bên thỏa thuận",
        "tự thỏa thuận", "tự quyết định", "do các bên", "do hai bên",
        "do chính phủ", "do thủ tướng", "do bộ trưởng", "do bộ ", "do ủy ban", "do ubnd",
        "do cơ quan có thẩm quyền", "do người có thẩm quyền", "do thủ trưởng", "do người đứng đầu",
        "giao chính phủ", "giao bộ trưởng", "giao bộ ", "giao ủy ban", "giao ubnd", "giao thủ trưởng",
        "giao cơ quan",
    )):
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


def _noi_khong_lap(doan: list[str | None]) -> str:
    """Noi cac doan bang xuong dong, bo doan rong hoac da nam trong phan da noi (so theo khoang trang chuan)."""
    giu: list[str] = []
    for d in doan:
        d = (d or "").strip()
        if d and " ".join(d.split()) not in " ".join(" ".join(giu).split()):
            giu.append(d)
    return "\n".join(giu)


def _gop_anh_em(paths: dict[str, dict]) -> dict[str, dict]:
    """Gop don vi ANH EM (>=2 con cung cha) len cha, lap den khi on dinh.

    Cha chi duoc gop khi la Khoan ('K') hoac Dieu ('D'): Diem anh em -> Khoan,
    Khoan anh em -> Dieu (khong leo len Chuong/Muc/Phan). Con LE giu nguyen cap cua no
    (vd 1 Diem le -> van la Diem). Mutate & tra lai chinh dict do.
    """
    def cha(p: str) -> str:
        return p.rsplit(">", 1)[0] if ">" in p else ""

    def cha_la_khoan_dieu(c: str) -> bool:
        return c.rsplit(">", 1)[-1][:1] in ("K", "D")

    while True:
        con_theo_cha: dict[str, list[str]] = {}
        for p in paths:
            c = cha(p)
            if c and cha_la_khoan_dieu(c):
                con_theo_cha.setdefault(c, []).append(p)
        muc = next((c for c, cons in con_theo_cha.items() if len(cons) >= 2), None)
        if muc is None:
            return paths
        cons = con_theo_cha[muc]
        vb = paths[cons[0]]["vb"]
        rank = min(paths[c]["rank"] for c in cons)
        rrf = max(paths[c]["rrf"] for c in cons)
        for c in cons:
            del paths[c]
        ex = paths.get(muc)
        if ex:
            ex["rank"], ex["rrf"] = min(ex["rank"], rank), max(ex["rrf"], rrf)
        else:
            paths[muc] = {"vb": vb, "rank": rank, "rrf": rrf}


def nap_khoan_ung_vien(conn, chunk_ids: list[str], diem_rrf: dict[str, float],
                       query: str | None = None, top_n: int | None = None) -> list[dict]:
    """Chon can cu ung vien cho LLM. Rerank TRUOC o muc chunk, GOP SAU ve don vi.

    3 buoc:
    1. Rerank o muc CHUNK (chua gop) theo query -> lay top_n chunk tot nhat. Khong co
       query/RERANK_URL -> sap theo diem_rrf roi cat top_n.
    2. Gop chunk da chon ve DON VI theo _gop_anh_em: nhieu Diem cung Khoan -> ca KHOAN;
       nhieu Khoan cung Dieu -> ca DIEU; mot Diem/Khoan le -> giu nguyen cap do.
    3. Build noi_dung day du (ten Dieu + than don vi + con chau), Phan/Chuong,
       loai_rang_buoc, tac_dong. Giu thu tu rerank.
    """
    if not chunk_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.id, c.text_embed, n.van_ban_id, n.cap, n.duong_dan FROM chunk c "
            "JOIN node n ON n.id = c.node_id WHERE c.id = ANY(%s)",
            (chunk_ids,),
        )
        chunks = [
            {"cid": cid, "text": te or "", "vb": vb, "cap": cap, "dd": dd,
             "rrf": diem_rrf.get(cid, 0.0)}
            for cid, te, vb, cap, dd in cur.fetchall()
        ]
    chunks.sort(key=lambda x: -x["rrf"])

    # Buoc 1: rerank muc CHUNK (truoc khi gop). rerank() tu fallback neu khong co RERANK_URL.
    if query and top_n:
        chunks = rerank(query, chunks, top_n, khoa_text="text")
    elif top_n:
        chunks = chunks[:top_n]

    # Buoc 2: don vi ban dau = duong_dan chunk da chon, roi gop anh em len cha (giu rank/rrf tot nhat)
    don_vi_info: dict[str, dict] = {}
    for rank, ch in enumerate(chunks):
        g = don_vi_info.get(ch["dd"])
        if g is None:
            don_vi_info[ch["dd"]] = {"vb": ch["vb"], "rank": rank, "rrf": ch["rrf"]}
        else:
            g["rank"], g["rrf"] = min(g["rank"], rank), max(g["rrf"], ch["rrf"])
    _gop_anh_em(don_vi_info)
    don_vi = sorted(((d["vb"], p, d["rank"], d["rrf"]) for p, d in don_vi_info.items()),
                    key=lambda x: x[2])   # (vb, unit_path, rank, rrf) theo thu tu rerank

    # Buoc 3: build noi_dung day du cho tung don vi
    out: list[dict] = []
    with conn.cursor() as cur:
        for vb_id, up, rank, rrf in don_vi:
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
            so_khoan = unit_stt if unit_cap == "khoan" else None
            diem = None
            if unit_cap == "diem":                 # don vi la Diem: lay them so Khoan cha
                diem = unit_stt
                kp = _unit_path(up)
                if kp != up:
                    cur.execute(
                        "SELECT so_thu_tu FROM node WHERE van_ban_id=%s AND duong_dan=%s AND cap='khoan'",
                        (vb_id, kp),
                    )
                    if rk := cur.fetchone():
                        so_khoan = rk[0]
            # than = don vi + toan bo con chau, theo thu tu
            cur.execute(
                "SELECT noi_dung FROM node WHERE van_ban_id=%s "
                "AND (duong_dan=%s OR duong_dan LIKE %s) ORDER BY order_index",
                (vb_id, up, up + ">%"),
            )
            # Node Dieu thuong da chua san toan van cac Khoan con -> bo doan da co de khong lap.
            noi_dung = _noi_khong_lap(
                [ten_dieu] + [html_doc_to_text(r[0] or "") for r in cur.fetchall()]
            )
            cur.execute("SELECT so_hieu, ten FROM van_ban WHERE id=%s", (vb_id,))
            vb = cur.fetchone() or (None, None)
            out.append({
                "khoan_id": unit_id,
                "van_ban_id": vb_id,
                "so_hieu": vb[0] or "", "ten_van_ban": vb[1] or "",
                "so_dieu": so_dieu, "tieu_de_dieu": ten_dieu,
                "so_khoan": so_khoan,
                "diem": diem,
                "phan": phan,
                "chuong": chuong,
                "noi_dung": noi_dung,
                "loai_rang_buoc": _loai_rang_buoc(noi_dung),
                "diem_rrf": rrf,
                "_rank": rank,
            })

    # Tac dong cap dieu khoan: can cu co bi sua doi/thay the/bai bo khong (ke ca mark o Dieu cha).
    # Dua NOI DUNG SAU KHI SUA len dau can cu de LLM lay lam chuan.
    impacts = impacts_cho_nodes(conn, [u["khoan_id"] for u in out])
    ngay_iso = date.today().isoformat()
    for u in out:
        td = impacts.get(u["khoan_id"])
        if td:
            u["tac_dong"] = td
            khoi = khoi_tac_dong(td, ngay_iso)
            if khoi:
                u["noi_dung"] = khoi + "\n" + u["noi_dung"]  # prepend de khong bi cat khi [:N]
    out.sort(key=lambda x: x["_rank"])   # giu thu tu rerank
    for u in out:
        u.pop("_rank", None)
    return out
