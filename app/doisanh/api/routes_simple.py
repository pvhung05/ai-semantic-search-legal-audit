"""4 API gon: /ask, /upload/legal, /upload/draft, /audit. Chi routing: parse request ->
goi service (audit/so_sanh, qa/chat, ingestion) -> tra JSON. Logic o module tuong ung."""
from __future__ import annotations

import json
import logging
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.db.session import ket_noi
from app.core.models.schemas import VanBanMeta
from app.doisanh.api import file_store
from app.doisanh.audit.docx_track import danh_dau_vi_pham
from app.doisanh.audit.segment import DonViSegment, segment_du_thao
from app.doisanh.audit.so_sanh import chay_tier2, chunk_embed_text, parse_vec
from app.doisanh.audit.tier1 import chay_tier1
from app.doisanh.db import repo_tai_lieu as rt
from app.doisanh.ingestion.loader import doc_file
from app.doisanh.ingestion.pipeline import nap_van_ban
from app.doisanh.public_loader import tac_dong_tom_tat
from app.doisanh.qa.chat import hoi_dap

logger = logging.getLogger(__name__)
router = APIRouter(tags=["simple"])


# ============================================================
# 1) /ask
# ============================================================
class LichSuChat(BaseModel):
    hoi: str = ""
    dap: str = ""


class AskRequest(BaseModel):
    cau_hoi: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(8, ge=1, le=20)
    is_local: Optional[bool] = Field(
        None, description="None=theo .env; true=Qwen local; false=Claude",
    )
    think: Optional[bool] = Field(None, description="Chi model local: bat/tat thinking. None=theo .env")
    lich_su: list[LichSuChat] = Field(
        default_factory=list, description="Cac luot hoi-dap truoc (nho theo HISTORY_CHAT)",
    )


@router.post("/ask")
def ask(req: AskRequest) -> dict:
    try:
        with ket_noi() as conn:
            return hoi_dap(
                conn, req.cau_hoi, top_k=req.top_k, is_local=req.is_local, think=req.think,
                lich_su=[l.model_dump() for l in req.lich_su],
            )
    except Exception as exc:
        logger.exception("/ask loi")
        raise HTTPException(500, str(exc)) from exc


# ============================================================
# 2a) /legal - danh sach van ban trong kho (co the dung lam van_ban_me_ids)
# ============================================================
@router.get("/api/legal/loai")
def danh_sach_loai() -> list[str]:
    """Danh sach loai van ban co thuc trong kho (de do vao filter)."""
    with ket_noi() as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT loai FROM van_ban WHERE loai IS NOT NULL ORDER BY loai")
        return [r[0] for r in cur.fetchall()]


@router.get("/api/legal")
def danh_sach_legal(
    con_hieu_luc: bool = True,
    q: str | None = None,
    loai: str | None = None,
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Danh sach VB trong kho, phan trang server-side (limit/offset) + tim theo ten/so_hieu (q).

    Tra ve {"total": tong_so, "items": [...]} de client dung cho phan trang.
    """
    ngay = date.today()
    dem_dieu = "(SELECT COUNT(*) FROM node n WHERE n.van_ban_id=v.id AND n.cap='dieu') AS so_dieu"
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    dk: list[str] = []
    params: list = []
    if con_hieu_luc:
        dk.append("(v.ngay_het_hieu_luc IS NULL OR v.ngay_het_hieu_luc > %s)")
        dk.append("(v.ngay_hieu_luc IS NULL OR v.ngay_hieu_luc <= %s)")
        params += [ngay, ngay]
    if q:
        dk.append("(v.ten ILIKE %s OR v.so_hieu ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if loai:
        dk.append("v.loai = %s")
        params.append(loai)
    if tu_ngay:
        dk.append("v.ngay_hieu_luc >= %s")
        params.append(tu_ngay)
    if den_ngay:
        dk.append("v.ngay_hieu_luc <= %s")
        params.append(den_ngay)
    where = ("WHERE " + " AND ".join(dk)) if dk else ""
    with ket_noi() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM van_ban v {where}", params)
        total = cur.fetchone()[0]
        cur.execute(
            f"""SELECT v.id, v.so_hieu, v.ten, v.loai,
                       v.ngay_hieu_luc, v.ngay_het_hieu_luc, {dem_dieu}
                FROM van_ban v {where}
                ORDER BY v.so_hieu LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        cols = [c.name for c in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {"total": total, "items": items}


# ============================================================
# 2a') /legal/{id}/html - xem toan van HTML vbpl da crawl
# ============================================================
@router.get("/legal/{van_ban_id}/html", response_class=HTMLResponse)
def xem_html(van_ban_id: str) -> HTMLResponse:
    """Tra toan van HTML (da crawl ve) de xem truc tiep tren trinh duyet."""
    with ket_noi() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT dc.noidung_html, v.so_hieu, v.ten
               FROM van_ban v
               LEFT JOIN document_content dc ON dc.document_id = v.id
               WHERE v.id = %s""",
            (van_ban_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Khong co van ban")
    noi_dung, so_hieu, ten = row
    if not noi_dung:
        raise HTTPException(404, "Van ban chua co toan van HTML")
    khung = (
        f"<!DOCTYPE html><html lang='vi'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{so_hieu or van_ban_id}</title>"
        f"<style>body{{max-width:900px;margin:24px auto;padding:0 16px;"
        f"font-family:system-ui,Arial,sans-serif;line-height:1.6;color:#1a1a1a}}"
        f"img{{max-width:100%;height:auto}}table{{max-width:100%}}</style></head>"
        f"<body>{noi_dung}</body></html>"
    )
    return HTMLResponse(khung)


# ============================================================
# 2b) /upload/legal
# ============================================================
@router.post("/upload/legal")
async def upload_legal(
    file: UploadFile = File(..., description="PDF/DOCX/TXT cua van ban luat"),
    meta_json: str = Form(..., description="JSON VanBanMeta: id, so_hieu, ten, loai, cap, ..."),
) -> dict:
    try:
        meta = VanBanMeta(**json.loads(meta_json))
    except Exception as exc:
        raise HTTPException(400, f"meta_json khong hop le: {exc}") from exc

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=Path(file.filename or "x").suffix,
    ) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        kq = nap_van_ban(tmp_path, meta, hieu_luc_tu=meta.ngay_hieu_luc)
        return {"van_ban_id": meta.id, **kq}
    finally:
        tmp_path.unlink(missing_ok=True)


# ============================================================
# 3) /upload/draft - chi nhan file
# ============================================================
@router.post("/upload/draft")
async def upload_draft(
    file: UploadFile = File(..., description="PDF/DOCX/TXT du thao"),
) -> dict:
    """Chi can file. Tu dong segment thanh Khoan/Diem/doan, luu DB, tra ve chunk."""
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=Path(file.filename or "x").suffix,
    ) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        try:
            text = doc_file(tmp_path)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        tai_lieu_id = rt.sinh_id_tai_lieu()
        file_store.luu_file_goc(tai_lieu_id, tmp_path, file.filename)   # giu ban goc + ten de track-change sau
        seg = segment_du_thao(text, tai_lieu_id)
        with ket_noi() as conn:
            rt.luu_du_thao(conn, tai_lieu_id, text, seg)
            conn.commit()
            # Sinh embedding cho tung don vi du thao (idempotent, commit theo batch).
            rt.nhung_du_thao_thieu(conn, tai_lieu_id)
    finally:
        tmp_path.unlink(missing_ok=True)

    chunks = [
        {
            "id": dv.id, "cap": dv.cap,
            "so_dieu": dv.so_dieu, "so_khoan": dv.so_khoan, "diem": dv.diem,
            "cau_goc": dv.noi_dung,
            "cau_de_doi_sanh": chunk_embed_text(dv),
        }
        for dv in seg.don_vi
    ]
    return {
        "tai_lieu_id": tai_lieu_id,
        "so_don_vi": len(chunks),
        "co_cau_truc_dieu": seg.co_cau_truc_dieu,
        "can_cu_tho": seg.can_cu_tho,
        "chunks": chunks,
    }


# ============================================================
# 4) /audit - khong can VB me. Moi chunk: hybrid search toan DB -> LLM so sanh.
# ============================================================
class AuditRequest(BaseModel):
    tai_lieu_id: str
    top_k: int = Field(8, ge=1, le=10,
                       description="(Khong con dung) so ung vien gui LLM nay do RERANK_TOP_N quyet dinh")
    van_ban_me_ids: Optional[list[str]] = Field(
        None,
        description="Tuy chon. Neu co: chi tim trong cac VB me nay. Neu rong: tim toan kho.",
    )
    is_local: Optional[bool] = Field(
        None, description="None=theo .env; true=Qwen local; false=Claude",
    )
    think: Optional[bool] = Field(None, description="Chi model local: bat/tat thinking. None=theo .env")


def _chay_tier1(don_vi_list: list, can_cu_tho: list, ngay: date) -> list[dict]:
    """Tier1 (dan chieu/hieu luc) con bam schema cu -> gated theo settings.ENABLE_TIER1.
    shortcut: tat mac dinh cho den khi port tier1 sang node/tac_dong."""
    if not settings.ENABLE_TIER1:
        return []
    out: list[dict] = []
    with ket_noi() as conn:
        ph = chay_tier1(conn, don_vi_list, ngay,
                        van_ban_me_ids=[], can_cu_tho=can_cu_tho or [],
                        cap_tai_lieu=None)
        vb_ids = {p.can_cu.van_ban_id for p in ph if p.can_cu and p.can_cu.van_ban_id}
        vb_map = {}
        if vb_ids:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, so_hieu, ten FROM van_ban WHERE id = ANY(%s)",
                    (list(vb_ids),),
                )
                vb_map = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        for p in ph:
            vb = vb_map.get(p.can_cu.van_ban_id if p.can_cu else None, ("", ""))
            out.append({
                "don_vi_id": p.don_vi_id, "trang_thai": "VI_PHAM",
                "loai_loi": p.loai_loi, "tin_cay": p.tin_cay,
                "doan_du_thao": p.doan_du_thao or "",
                "so_hieu": vb[0], "ten_van_ban": vb[1],
                "trich_dan": p.can_cu.trich_dan if p.can_cu else "",
                "giai_thich": p.giai_thich or "",
                "de_xuat_sua": p.de_xuat_sua or "",
            })
    return out


@router.post("/audit")
def audit(req: AuditRequest) -> dict:
    """Khong can linh_vuc / VB me. Voi moi chunk du thao:
    1. Hybrid search top-k Khoan gan nhat (toan kho).
    2. Goi LLM so sanh chunk vs top-k -> phat hien VI_PHAM / HOP_LE.

    Them: tier1 kiem can cu het hieu luc trong 'Can cu' cua du thao.
    """
    ngay = date.today()
    with ket_noi() as conn:
        dt = rt.doc_du_thao(conn, req.tai_lieu_id)
        if dt is None:
            raise HTTPException(404, f"tai_lieu_id '{req.tai_lieu_id}' khong ton tai")
        rows = rt.danh_sach_don_vi(conn, req.tai_lieu_id)
    can_cu_tho = dt["can_cu_tho"]
    trich_yeu = dt.get("trich_yeu", "")   # chu de chung -> gui kem prompt de loc can cu khac linh vuc
    don_vi_list = [DonViSegment(
        id=r["id"], cap=r["cap"], so_dieu=r["so_dieu"], so_khoan=r["so_khoan"],
        diem=r["diem"], tieu_de=r["tieu_de"], noi_dung=r["noi_dung"],
        hash="", thu_tu=r["thu_tu"], parent_id=r["parent_id"],
    ) for r in rows]
    emb_by_id = {r["id"]: parse_vec(r["embedding"]) for r in rows if r.get("embedding")}
    if not don_vi_list:
        raise HTTPException(422, "Du thao chua co don vi nao, hay upload lai")

    tier1_phat_hien = _chay_tier1(don_vi_list, can_cu_tho, ngay)
    tier2_kq = chay_tier2(
        don_vi_list, emb_by_id, trich_yeu=trich_yeu, ngay=ngay,
        van_ban_me_ids=req.van_ban_me_ids, is_local=req.is_local, think=req.think,
    )

    ngay_iso = ngay.isoformat()
    nhom: dict[str, list[dict]] = {"VI_PHAM": [], "HOP_LE": [], "CHUA_XAC_DINH": []}
    for k in tier1_phat_hien + tier2_kq:
        tag = k.get("trang_thai", "CHUA_XAC_DINH")
        cc = {
            "so_hieu": k.get("so_hieu", ""),
            "ten_van_ban": k.get("ten_van_ban", ""),
            "vi_tri": k.get("cc_vi_tri", ""),
            "trich_dan": k.get("trich_dan", ""),        # phan CHUA sua (noi dung hien hanh)
        }
        bsd = tac_dong_tom_tat(k.get("tac_dong"), ngay_iso)
        if bsd:                                          # phan SAU khi sua (neu co)
            cc["da_sua"] = True
            cc["sua_boi"] = bsd["nguon"]
            cc["ngay_hieu_luc"] = bsd["ngay_hieu_luc"]
            cc["da_het_hieu_luc"] = bsd["da_het_hieu_luc"]
            cc["noi_dung_sau_sua"] = bsd["noi_dung_sau_sua"]
        nhom[tag].append({
            "don_vi_id": k["don_vi_id"],   # can cho UI to mau don vi du thao (xanh/do/vang)
            "noi_dung_du_thao": k.get("doan_du_thao", ""),
            "can_cu_phap_ly": cc,
            "de_xuat_sua": k.get("de_xuat_sua", ""),
        })

    return {
        "tai_lieu_id": req.tai_lieu_id,
        "thong_ke": {k: len(v) for k, v in nhom.items()},
        "ket_qua": nhom,
    }


@router.post("/audit/docx")
def audit_docx(req: AuditRequest) -> dict:
    """Y HET /audit (input JSON {tai_lieu_id, top_k, ...}), NHUNG ngoai JSON ket qua con
    LUU ra file '<ten_goc>_track_changes.docx' (to mau DO cac doan VI_PHAM + comment
    'AI LEGAL': trich_dan can cu + de_xuat_sua) de nguoi dung tai ve.

    Tra ve: toan bo JSON cua /audit + `so_danh_dau` + `ten_file` + `tai_file`
    (URL GET de tai). Null neu ban goc khong phai .docx / khong tim thay.
    """
    ket = audit(req)
    so_danh_dau = 0
    ten_file: str | None = None
    src = file_store.file_goc(req.tai_lieu_id)
    if src is not None and src.suffix.lower() == ".docx":
        out = file_store.duong_dan_output(req.tai_lieu_id, src.stem)
        try:
            so_danh_dau = danh_dau_vi_pham(src, ket, out)
        except Exception as exc:
            logger.exception("Danh dau docx loi: %s", exc)
            raise HTTPException(500, f"Khong danh dau duoc docx: {exc}")
        ten_file = out.name
    return {
        **ket,
        "so_danh_dau": so_danh_dau,
        "ten_file": ten_file,
        "tai_file": f"/audit/docx/{req.tai_lieu_id}" if ten_file else None,
    }


@router.delete("/draft")
def xoa_tat_ca_draft() -> dict:
    """Clear TOAN BO du thao trong rag (du_thao + du_thao_node) + file da luu. De upload lai tu dau."""
    with ket_noi() as conn:
        n = rt.xoa_tat_ca_du_thao(conn)
        conn.commit()
    file_store.xoa_tat_ca_file()
    return {"da_xoa": n}


@router.delete("/draft/{tai_lieu_id}")
def xoa_draft(tai_lieu_id: str) -> dict:
    """Xoa 1 du thao (du_thao + du_thao_node cascade) + file goc/track-change da luu."""
    with ket_noi() as conn:
        n = rt.xoa_du_thao(conn, tai_lieu_id)
        conn.commit()
    file_store.xoa_file(tai_lieu_id)
    if not n:
        raise HTTPException(404, f"tai_lieu_id '{tai_lieu_id}' khong ton tai")
    return {"tai_lieu_id": tai_lieu_id, "da_xoa": True}


@router.get("/audit/docx/{tai_lieu_id}")
def tai_file_track_changes(tai_lieu_id: str) -> FileResponse:
    """Tai file '<ten_goc>_track_changes.docx' da tao o POST /audit/docx (data/track_changes)."""
    f = file_store.tim_file_track_change(tai_lieu_id)
    if f is None:
        raise HTTPException(404, "Chua co file track-changes. Goi POST /audit/docx truoc.")
    return FileResponse(
        str(f), filename=f.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
