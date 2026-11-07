"""Nap CAY noi dung (cay tho da cao, luu o `vanban.document_cay`) vao schema `public`.

Service doi sanh so huu buoc nay: doc cay tho tu `meta` (do service crawl ghi) roi
dung `vanban.node` + `rag.chunk`. KHONG goi mang ra vbpl.vn.

Mot node = mot dong `vanban.node` (Chuong/Muc/Dieu/Khoan/Diem), khoa = UUID vbpl.
Node la -> sinh `rag.chunk` (text da lam sach, chua embedding - de GD embedding sau).
`vanban.van_ban` lay lai metadata tu `vanban.documents` (nguon metadata duy nhat).

save_cay idempotent: xoa sach node cu cua van_ban roi nap lai (chunk CASCADE theo node).
"""
from __future__ import annotations

import logging
import re
from datetime import date

import psycopg

from app.core.config import settings
from app.core.html_text import html_doc_to_text
from app.core.models.embedder import embed_batch

log = logging.getLogger(__name__)

# level (API) -> cap_node (enum public)
# Thu bac: Part > Chapter > Section > Article > Clause > Point
_LEVEL_CAP = {
    "Part":    "phan",
    "Chapter": "chuong",
    "Section": "muc",
    "Article": "dieu",
    "Clause":  "khoan",
    "Point":   "diem",
}
_CAP_PREFIX = {"phan": "P", "chuong": "C", "muc": "M", "dieu": "D", "khoan": "K", "diem": "d"}


def tach_duong_dan(duong_dan: str | None) -> dict[str, str | None]:
    """Tach duong_dan ('C1>D5>K2>da') -> {so_dieu, so_khoan, diem} de dinh danh can cu.

    Moi doan = prefix (xem _CAP_PREFIX) + so_thu_tu. 'D'=dieu, 'K'=khoan, 'd'=diem (phan biet hoa/thuong).
    """
    out: dict[str, str | None] = {"so_dieu": None, "so_khoan": None, "diem": None}
    for seg in (duong_dan or "").split(">"):
        if len(seg) < 2 or seg[1:] == "?":
            continue
        p, val = seg[0], seg[1:]
        if p == "D":
            out["so_dieu"] = val
        elif p == "K":
            out["so_khoan"] = val
        elif p == "d":
            out["diem"] = val
    return out

# trang thai hop le cua vanban.trangthai_node
_NODE_TT = {
    "chua_hieu_luc", "con_hieu_luc", "het_hieu_luc_mot_phan",
    "het_hieu_luc", "bai_bo", "khong_xac_dinh",
}

_RE_STT = {
    "phan":   re.compile(r"Phần\s+(thứ\s+\S+|[IVXLCDM0-9]+[A-Za-zđ]?)", re.I),
    "chuong": re.compile(r"Chương\s+([IVXLCDM0-9]+[A-Za-zđ]?)", re.I),
    "muc":    re.compile(r"Mục\s+([0-9IVXLCDM]+[A-Za-zđ]?)", re.I),
    "dieu":   re.compile(r"Điều\s+(\d+[a-zđ]?)", re.I),
    "khoan":  re.compile(r"Khoản\s+(\d+[a-zđ]?)", re.I),
    "diem":   re.compile(r"Điểm\s+([a-zđ0-9]+)", re.I),
}
_RE_STT_FALLBACK = {
    "khoan": re.compile(r"^\s*(\d+[a-zđ]?)\s*[\.\)]"),
    "diem":  re.compile(r"^\s*([a-zđ])\s*\)"),
}


def _map_trang_thai(meta_val: str | None) -> str:
    v = (meta_val or "").strip().lower()
    return v if v in _NODE_TT else "khong_xac_dinh"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _so_thu_tu(cap: str, node: dict) -> str | None:
    content = node.get("content") or {}
    title = (content.get("title") or node.get("title") or "").split("\n")[0]
    rx = _RE_STT.get(cap)
    m = rx.search(title) if rx else None
    if not m and cap in _RE_STT_FALLBACK:
        m = _RE_STT_FALLBACK[cap].search(title)
    return m.group(1) if m else None


def _flatten(tree: list[dict], van_ban_id: str) -> list[dict]:
    """Duyet pre-order (cha truoc con) de thoa FK self-reference parent_id."""
    rows: list[dict] = []

    def walk(nodes: list[dict], parent_id: str | None, path: str) -> None:
        for n in nodes:
            nid = n.get("id") or n.get("key")
            level = n.get("level")
            cap = _LEVEL_CAP.get(level or "")
            if not nid:
                log.warning("node khong co id (level=%s), bo qua", level)
                continue
            if cap is None:
                # Level la: bo node nay nhung GIU con (noi vao parent hien tai) de khong mat noi dung
                log.warning("level '%s' chua map (node %s), bo node - giu nhanh con", level, nid)
                walk(n.get("children") or [], parent_id, path)
                continue
            stt = _so_thu_tu(cap, n)
            seg = _CAP_PREFIX[cap] + (stt or "?")
            duong_dan = f"{path}>{seg}" if path else seg
            content = n.get("content") or {}
            rows.append({
                "id": nid,
                "van_ban_id": van_ban_id,
                "parent_id": parent_id,
                "cap": cap,
                "ptype": n.get("ptype"),
                "so_thu_tu": stt,
                "tieu_de": (n.get("title") or "").strip() or None,
                "noi_dung": content.get("content"),
                "order_index": n.get("orderIndex"),
                "is_leaf": bool(n.get("isLeaf")),
                "duong_dan": duong_dan,
                "hieu_luc_tu": _parse_date(n.get("effFrom")),
                "hieu_luc_den": _parse_date(n.get("effTo")),
            })
            walk(n.get("children") or [], nid, duong_dan)

    walk(tree, None, "")
    return rows


def _content_khong_title(noi_dung: str | None, tieu_de: str | None) -> str:
    """clean(noi_dung) nhung bo tieu_de lap o dau (content cap Dieu lap lai title)."""
    text = html_doc_to_text(noi_dung or "").strip()
    td = (tieu_de or "").strip()
    if td and text.startswith(td):
        text = text[len(td):].lstrip(" \n.:-")
    return text


def _text_embed(r: dict, by_id: dict[str, dict]) -> str:
    """Ghep text_embed theo cap + ngu canh cha truc tiep:
    - Dieu la : content Dieu (bo title).
    - Khoan la: title Dieu cha + content Khoan (bo title).
    - Diem la : content Khoan cha + content Diem (bo title).
    shortcut: dung parent truc tiep lam Dieu/Khoan cha, dung cho cay chuan;
    neu xuat hien Khoan nam truc tiep duoi Chuong thi sua lai tim to tien theo cap.
    """
    noi_dung = _content_khong_title(r["noi_dung"], r["tieu_de"])
    cha = by_id.get(r["parent_id"]) if r["parent_id"] else None
    if r["cap"] == "khoan":
        tieu_de_cha = (cha["tieu_de"] if cha else "") or ""
        return "\n".join(p for p in (tieu_de_cha, noi_dung) if p)
    if r["cap"] == "diem":
        nd_cha = html_doc_to_text(cha["noi_dung"] or "").strip() if cha else ""
        return "\n".join(p for p in (nd_cha, noi_dung) if p)
    return noi_dung


def _upsert_van_ban(cur: psycopg.Cursor, van_ban_id: str) -> None:
    cur.execute(
        """SELECT d.so_hieu, d.tieu_de, lv.ten, d.ngay_banhanh, d.ngay_hieuluc,
                  d.ngay_hethieuluc, d.trangthai::text
           FROM vanban.documents d
           LEFT JOIN danhmuc.loai_vanban lv ON lv.id = d.loai_vanban_id
           WHERE d.id = %s""",
        (van_ban_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"van ban {van_ban_id} chua co trong vanban.documents (FK)")
    so_hieu, ten, loai, nbh, nhl, nhhl, tt = row
    cur.execute(
        """INSERT INTO vanban.van_ban
             (id, so_hieu, ten, loai, ngay_ban_hanh, ngay_hieu_luc, ngay_het_hieu_luc, trang_thai)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO UPDATE SET
             so_hieu=EXCLUDED.so_hieu, ten=EXCLUDED.ten, loai=EXCLUDED.loai,
             ngay_ban_hanh=EXCLUDED.ngay_ban_hanh, ngay_hieu_luc=EXCLUDED.ngay_hieu_luc,
             ngay_het_hieu_luc=EXCLUDED.ngay_het_hieu_luc, trang_thai=EXCLUDED.trang_thai""",
        (van_ban_id, so_hieu, ten, loai, nbh, nhl, nhhl, _map_trang_thai(tt)),
    )


def save_cay(conn: psycopg.Connection, van_ban_id: str, tree: list[dict]) -> dict[str, int]:
    """Nap cay vao vanban.node + rag.chunk. Tra ve so luong da ghi."""
    van_ban_id = str(van_ban_id).strip()
    rows = _flatten(tree, van_ban_id)

    with conn.cursor() as cur:
        _upsert_van_ban(cur, van_ban_id)
        # idempotent: xoa node cu (chunk CASCADE theo node)
        cur.execute("DELETE FROM vanban.node WHERE van_ban_id = %s", (van_ban_id,))

        cur.executemany(
            """INSERT INTO vanban.node
                 (id, van_ban_id, parent_id, cap, ptype, so_thu_tu, tieu_de, noi_dung,
                  order_index, is_leaf, duong_dan, hieu_luc_tu, hieu_luc_den)
               VALUES (%(id)s, %(van_ban_id)s, %(parent_id)s, %(cap)s, %(ptype)s, %(so_thu_tu)s,
                       %(tieu_de)s, %(noi_dung)s, %(order_index)s, %(is_leaf)s, %(duong_dan)s,
                       %(hieu_luc_tu)s, %(hieu_luc_den)s)""",
            rows,
        )

        by_id = {r["id"]: r for r in rows}
        chunks = []
        for r in rows:
            if not r["is_leaf"] or not r["noi_dung"]:
                continue
            text = html_doc_to_text(r["noi_dung"]).strip()
            if not text:
                continue
            # node chi co tieu de (content = title) -> text_embed rong -> fallback text_goc
            embed_text = _text_embed(r, by_id) or text
            chunks.append((r["id"], van_ban_id, text, embed_text,
                           r["hieu_luc_tu"], r["hieu_luc_den"]))
        if chunks:
            cur.executemany(
                """INSERT INTO rag.chunk
                     (node_id, van_ban_id, text_goc, text_embed, hieu_luc_tu, hieu_luc_den)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                chunks,
            )

    return {"node": len(rows), "chunk": len(chunks)}


def nhung_chunk_thieu(
    conn: psycopg.Connection, van_ban_id: str | None = None, batch_size: int | None = None
) -> int:
    """Sinh embedding cho chunk co embedding IS NULL (tu text_embed). Tra so chunk da nhung.

    Loc theo van_ban_id neu truyen. Commit theo tung batch -> chay lai idempotent.
    """
    bs = batch_size or settings.EMBED_BATCH_SIZE
    sql = (
        "SELECT id, text_embed FROM rag.chunk "
        "WHERE embedding IS NULL AND text_embed IS NOT NULL AND text_embed <> ''"
    )
    params: list = []
    if van_ban_id:
        sql += " AND van_ban_id = %s"
        params.append(str(van_ban_id).strip())
    sql += " ORDER BY id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    da = 0
    for i in range(0, len(rows), bs):
        lo = rows[i : i + bs]
        embs = embed_batch([t for _, t in lo])
        with conn.cursor() as cur:
            for (cid, _), emb in zip(lo, embs):
                if len(emb) != settings.EMBED_DIM:
                    raise ValueError(f"chunk {cid}: embedding {len(emb)}d != EMBED_DIM {settings.EMBED_DIM}")
                emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
                cur.execute("UPDATE rag.chunk SET embedding = %s::vector WHERE id = %s", (emb_str, cid))
        conn.commit()
        da += len(lo)
    return da


# vbpl_code -> enum loai_tacdong (chi cac ma phat sinh o cap dieu khoan).
# Ma khac (2,3,4,5,6,7,14,15,17,18) la quan he cap van ban -> khong sinh tac_dong.
_CODE_LOAI = {
    "1": "bai_bo", "8": "huong_dan", "9": "huong_dan", "10": "sua_doi",
    "11": "dinh_chi", "12": "thay_the", "13": "bo_sung", "16": "sua_doi",
}


def port_impacts(conn: psycopg.Connection, van_ban_id: str) -> dict[str, int]:
    """Port vanban.provision_impacts -> vanban.tac_dong cho van ban van_ban_id (bi tac dong).

    Chi nhan canh co node dich ton tai trong vanban.node va ma loai map duoc sang
    enum loai_tacdong. node_nguon_id = NULL neu VB nguon chua build cay. Bao dam
    vanban.van_ban cua VB nguon ton tai (FK) qua _upsert_van_ban. Idempotent: xoa
    tac_dong cu cua cac node dich thuoc van ban nay roi nap lai.
    """
    van_ban_id = str(van_ban_id).strip()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM vanban.node WHERE van_ban_id = %s", (van_ban_id,))
        node_dich = {r[0] for r in cur.fetchall()}
        cur.execute(
            """SELECT pi.target_provision_id, pi.source_provision_id, pi.source_doc_id,
                      rt.vbpl_code, pi.relation_type_id, pi.eff_from, pi.eff_to,
                      pi.target_order_index, pi.content, pi.source_title
               FROM vanban.provision_impacts pi
               JOIN danhmuc.relation_types rt ON rt.id = pi.relation_type_id
               WHERE pi.target_doc_id = %s""",
            (van_ban_id,),
        )
        impacts = cur.fetchall()

        # node nguon nao da ton tai trong vanban.node?
        src_ids = [s for (_, s, *_rest) in impacts if s]
        node_nguon_co: set[str] = set()
        if src_ids:
            cur.execute("SELECT id FROM vanban.node WHERE id = ANY(%s)", (src_ids,))
            node_nguon_co = {r[0] for r in cur.fetchall()}

        cur.execute(
            "DELETE FROM vanban.tac_dong WHERE node_dich_id = ANY(%s)",
            (list(node_dich),),
        )

        n = bo_qua = 0
        vb_nguon_da_bao_dam: set[str] = set()
        for (tid, sid, src_doc, code, rel_id, eff_tu, eff_den, order_idx, content, src_title) in impacts:
            loai = _CODE_LOAI.get(str(code))
            if tid not in node_dich or loai is None or not src_doc:
                bo_qua += 1
                continue
            if src_doc not in vb_nguon_da_bao_dam:
                _upsert_van_ban(cur, src_doc)   # FK van_ban_nguon_id (du VB nguon chua build cay)
                vb_nguon_da_bao_dam.add(src_doc)
            cur.execute(
                """INSERT INTO vanban.tac_dong
                     (node_dich_id, node_nguon_id, van_ban_nguon_id, loai, relation_type_id,
                      ngay_hieu_luc, hieu_luc_den, order_index, noi_dung_moi, nguon_lenh, tin_cay)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'xac_nhan')""",
                (tid, sid if sid in node_nguon_co else None, src_doc, loai, rel_id,
                 eff_tu, eff_den, order_idx, content, src_title),
            )
            n += 1
    return {"tac_dong": n, "bo_qua": bo_qua}


def impacts_cho_nodes(conn: psycopg.Connection, node_ids: list[str]) -> dict[str, list[dict]]:
    """Voi moi node, tra tac dong nam tren CHINH no / TO TIEN / CON CHAU (theo duong_dan).

    Dung cho audit: biet can cu luat da bi sua doi/thay the chua (ke ca khi mark o Dieu
    cha ma du thao chi nhac Khoan con). Tra {node_id: [{loai, ten, van_ban_nguon_id,
    ngay_hieu_luc, noi_dung}]}. Rong neu vanban.tac_dong chua co du lieu.
    """
    if not node_ids:
        return {}
    out: dict[str, list[dict]] = {}
    with conn.cursor() as cur:
        cur.execute(
            """SELECT ref.id, td.loai::text, rt.ten_chieu_nguoc, td.van_ban_nguon_id,
                      td.ngay_hieu_luc, td.noi_dung_moi, vn.so_hieu, td.hieu_luc_den,
                      vn.ten, td.nguon_lenh
               FROM vanban.node ref
               JOIN vanban.node nd ON nd.van_ban_id = ref.van_ban_id
                    AND (ref.duong_dan = nd.duong_dan
                      OR ref.duong_dan LIKE nd.duong_dan || '>%%'
                      OR nd.duong_dan  LIKE ref.duong_dan || '>%%')
               JOIN vanban.tac_dong td ON td.node_dich_id = nd.id
               LEFT JOIN danhmuc.relation_types rt ON rt.id = td.relation_type_id
               LEFT JOIN vanban.van_ban vn ON vn.id = td.van_ban_nguon_id
               WHERE ref.id = ANY(%s)""",
            (node_ids,),
        )
        for nid, loai, ten, vb_nguon, ngay, noi_dung, so_hieu, den, ten_nguon, nguon_lenh in cur.fetchall():
            out.setdefault(nid, []).append({
                "loai": loai, "ten": ten, "van_ban_nguon_id": vb_nguon,
                "so_hieu_nguon": so_hieu, "ten_nguon": ten_nguon, "nguon_lenh": nguon_lenh,
                "ngay_hieu_luc": ngay.isoformat() if ngay else None,
                "hieu_luc_den": den.isoformat() if den else None,
                "noi_dung": noi_dung,
            })
    return out


def tac_dong_hieu_luc(td_list: list[dict] | None, ngay_iso: str) -> dict | None:
    """Tac dong con hieu luc & moi nhat tren 1 can cu (None neu khong co)."""
    con_hl = [
        t for t in (td_list or [])
        if not (t.get("ngay_hieu_luc") and t["ngay_hieu_luc"] > ngay_iso)   # chua hieu luc -> bo
        and not (t.get("hieu_luc_den") and t["hieu_luc_den"] < ngay_iso)     # da het -> bo
    ]
    if not con_hl:
        return None
    return max(con_hl, key=lambda x: x.get("ngay_hieu_luc") or "")


def nguon_tac_dong(t: dict) -> str:
    """Nguon tac dong de nguoi doc tim duoc: uu tien nguon_lenh (vi tri + ten luat,
    vd 'Khoan 2, Dieu 1 - Luat ... so 81/2025/QH15'); nguoc lai so hieu/ten/id."""
    return (t.get("nguon_lenh") or t.get("so_hieu_nguon")
            or t.get("ten_nguon") or t.get("van_ban_nguon_id") or "?")


def khoi_tac_dong(td_list: list[dict], ngay_iso: str) -> str:
    """Khoi van ban mo ta can cu da bi sua (chen dau noi_dung can cu gui LLM). Rong neu khong co."""
    t = tac_dong_hieu_luc(td_list, ngay_iso)
    if not t:
        return ""
    nguon, ngay = nguon_tac_dong(t), t.get("ngay_hieu_luc") or "?"
    nhan = (t.get("ten") or "bị tác động bởi").strip()
    if t.get("loai") == "bai_bo":
        return f"[CĂN CỨ NÀY {nhan} {nguon} (hiệu lực {ngay}) — ĐÃ HẾT HIỆU LỰC, không còn là căn cứ]"
    moi = html_doc_to_text(t.get("noi_dung") or "").strip()
    khoi = f"[CĂN CỨ NÀY {nhan} {nguon} (hiệu lực {ngay}) — DÙNG NỘI DUNG SAU KHI SỬA LÀM CHUẨN]"
    if moi:
        khoi += f"\nNội dung sau khi sửa: {moi}"
    return khoi


def tac_dong_tom_tat(td_list: list[dict] | None, ngay_iso: str) -> dict | None:
    """Tom tat tac dong de TRA VE ket qua (UI hien 'can cu da bi sua boi...'). None neu khong co."""
    t = tac_dong_hieu_luc(td_list, ngay_iso)
    if not t:
        return None
    het = t.get("loai") == "bai_bo"
    return {
        "loai": t.get("loai"),
        "nhan": t.get("ten"),
        "nguon": nguon_tac_dong(t),
        "ngay_hieu_luc": t.get("ngay_hieu_luc"),
        "da_het_hieu_luc": het,
        "noi_dung_sau_sua": "" if het else html_doc_to_text(t.get("noi_dung") or "").strip(),
    }


def doc_cay_tu_meta(cur: psycopg.Cursor, van_ban_id: str) -> list[dict] | None:
    """Doc cay tho da cao tu `vanban.document_cay`. None neu chua co."""
    cur.execute(
        "SELECT cay FROM vanban.document_cay WHERE document_id = %s",
        (str(van_ban_id).strip(),),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return row[0]


def build_cay_tu_meta(conn: psycopg.Connection, van_ban_id: str) -> dict[str, int]:
    """Dung vanban.node/chunk tu cay tho da luu o vanban.document_cay (khong goi mang).

    Raise ValueError neu van ban chua co cay trong meta (can chay crawl `fetch-cay` truoc).
    """
    van_ban_id = str(van_ban_id).strip()
    with conn.cursor() as cur:
        tree = doc_cay_tu_meta(cur, van_ban_id)
    if tree is None:
        raise ValueError(
            f"van ban {van_ban_id} chua co cay trong vanban.document_cay "
            f"(chay `python -m app.crawl.cli fetch-cay --id {van_ban_id}` truoc)"
        )
    return save_cay(conn, van_ban_id, tree)
