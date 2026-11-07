"""4 API gon: /ask, /upload/legal, /upload/draft, /audit."""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.doisanh.audit.docx_track import danh_dau_vi_pham
from app.doisanh.audit.prompts import prompt_tier2_khoan
from app.doisanh.audit.segment import segment_du_thao
from app.doisanh.audit.tier1 import chay_tier1
from app.core.config import settings
from app.doisanh.db import repo_tai_lieu as rt
from app.core.db.session import ket_noi
from app.doisanh.ingestion.loader import doc_file
from app.doisanh.ingestion.pipeline import nap_van_ban
from app.core.models.llm import goi_json
from app.core.models.schemas import VanBanMeta
from app.doisanh.public_loader import tac_dong_tom_tat
from app.doisanh.qa.chat import hoi_dap
from app.doisanh.retrieval.can_cu import nap_khoan_ung_vien
from app.doisanh.retrieval.hybrid import tim_hybrid, tim_hybrid_tu_text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["simple"])


def _parse_vec(s: str | None) -> list[float] | None:
    """pgvector tra ve dang text '[0.1,0.2,...]' -> list[float]. None neu rong."""
    if not s:
        return None
    s = s.strip().strip("[]")
    return [float(x) for x in s.split(",")] if s else None


# ============================================================
# 1) /ask
# ============================================================
class AskRequest(BaseModel):
    cau_hoi: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(8, ge=1, le=20)
    is_local: Optional[bool] = Field(
        None, description="None=theo .env; true=Qwen local; false=Claude",
    )


@router.post("/ask")
def ask(req: AskRequest) -> dict:
    try:
        with ket_noi() as conn:
            return hoi_dap(conn, req.cau_hoi, top_k=req.top_k, is_local=req.is_local)
    except Exception as exc:
        logger.exception("/ask loi")
        raise HTTPException(500, str(exc)) from exc


# ============================================================
# 2a) /legal - danh sach van ban trong kho (co the dung lam van_ban_me_ids)
# ============================================================
@router.get("/legal")
def danh_sach_legal(con_hieu_luc: bool = True) -> list[dict]:
    """Tra ve danh sach VB trong kho de nguoi dung chon van_ban_me_ids cho /audit."""
    ngay = date.today()
    dem_dieu = ("(SELECT COUNT(*) FROM node n WHERE n.van_ban_id=v.id AND n.cap='dieu') AS so_dieu")
    with ket_noi() as conn, conn.cursor() as cur:
        if con_hieu_luc:
            cur.execute(
                f"""SELECT v.id, v.so_hieu, v.ten, v.loai,
                           v.ngay_hieu_luc, v.ngay_het_hieu_luc, {dem_dieu}
                    FROM van_ban v
                    WHERE (v.ngay_het_hieu_luc IS NULL OR v.ngay_het_hieu_luc > %s)
                      AND (v.ngay_hieu_luc IS NULL OR v.ngay_hieu_luc <= %s)
                    ORDER BY v.so_hieu""",
                (ngay, ngay),
            )
        else:
            cur.execute(
                f"""SELECT v.id, v.so_hieu, v.ten, v.loai,
                           v.ngay_hieu_luc, v.ngay_het_hieu_luc, {dem_dieu}
                    FROM van_ban v ORDER BY v.so_hieu""",
            )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


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
def _chunk_embed_text(dv) -> str:
    return (dv.tieu_de + ". " + dv.noi_dung) if dv.tieu_de else (dv.noi_dung or "")


_DRAFT_DIR = settings.STORAGE_PATH / "drafts"              # ban goc du thao (giu ten upload)
_OUTPUT_DIR = settings.STORAGE_PATH.parent / "track_changes"  # = data/track_changes: ban da track-change
_HAU_TO_TC = "_track_changes"


def _luu_file_goc(tai_lieu_id: str, src: Path, ten_goc: str | None) -> None:
    """Luu ban goc giu nguyen TEN FILE upload (de dat ten ban track-change sau)."""
    folder = _DRAFT_DIR / tai_lieu_id
    folder.mkdir(parents=True, exist_ok=True)
    ten = Path(ten_goc or f"du_thao{src.suffix}").name
    shutil.copy(src, folder / ten)


def _file_goc(tai_lieu_id: str) -> Path | None:
    """File goc du thao da luu luc upload (moi folder chi co 1 file).

    Output track-change nam o _OUTPUT_DIR (thu muc khac), nen o day khong can
    loai tru *_track_changes: cu tra file dau tien tim thay.
    """
    folder = _DRAFT_DIR / tai_lieu_id
    if not folder.is_dir():
        return None
    for f in folder.iterdir():
        if f.is_file():
            return f
    return None


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
        _luu_file_goc(tai_lieu_id, tmp_path, file.filename)   # giu ban goc + ten de track-change sau
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
            "cau_de_doi_sanh": _chunk_embed_text(dv),
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
    top_k: int = Field(5, ge=1, le=10, description="So Khoan me ung vien moi chunk")
    van_ban_me_ids: Optional[list[str]] = Field(
        None,
        description="Tuy chon. Neu co: chi tim trong cac VB me nay. Neu rong: tim toan kho.",
    )
    is_local: Optional[bool] = Field(
        None, description="None=theo .env; true=Qwen local; false=Claude",
    )


def _so_sanh_chunk(dv_dict: dict, ung_vien: list[dict], is_local: bool | None = None) -> dict:
    """Goi LLM so sanh 1 chunk du thao voi top-k Khoan me. Tra 1 verdict object."""
    if not ung_vien:
        return {}
    doan = {
        "id": dv_dict["id"], "so_dieu": dv_dict.get("so_dieu"),
        "so_khoan": dv_dict.get("so_khoan"), "diem": dv_dict.get("diem"),
        "tieu_de": dv_dict.get("tieu_de"), "noi_dung": dv_dict["noi_dung"],
    }
    uv_rut_gon = [
        {
            "khoan_id": u["khoan_id"], "so_hieu": u["so_hieu"],
            "phan": u.get("phan"), "chuong": u.get("chuong"),
            "so_dieu": u["so_dieu"], "so_khoan": u["so_khoan"], "diem": u["diem"],
            "tieu_de_dieu": u["tieu_de_dieu"],
            "loai_rang_buoc": u.get("loai_rang_buoc", ["khong_ro"]),
            "noi_dung": u["noi_dung"][:2200],  # du cho khoi 'noi dung sau khi sua' o dau
        }
        for u in ung_vien
    ]
    messages = prompt_tier2_khoan(doan, uv_rut_gon, None, None)
    try:
        data = goi_json(messages, temperature=0.1, is_local=is_local)
    except Exception as exc:
        logger.warning("LLM so sanh loi don_vi=%s: %s", dv_dict["id"], exc)
        return {}
    # LLM tra ve 1 object; phong truong hop tra list hoac boc trong 'ket_qua'
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict) and "trang_thai" not in data:
        inner = data.get("ket_qua") or data.get("items")
        if isinstance(inner, list) and inner:
            data = inner[0]
        elif isinstance(inner, dict):
            data = inner
    return data if isinstance(data, dict) else {}


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
    cap_tai_lieu = None  # user khong cung cap cap tuong duong
    from app.doisanh.audit.segment import DonViSegment
    don_vi_list = [DonViSegment(
        id=r["id"], cap=r["cap"], so_dieu=r["so_dieu"], so_khoan=r["so_khoan"],
        diem=r["diem"], tieu_de=r["tieu_de"], noi_dung=r["noi_dung"],
        hash="", thu_tu=r["thu_tu"], parent_id=r["parent_id"],
    ) for r in rows]
    emb_by_id = {r["id"]: _parse_vec(r["embedding"]) for r in rows if r.get("embedding")}
    if not don_vi_list:
        raise HTTPException(422, "Du thao chua co don vi nao, hay upload lai")

    # Tier1 (dan chieu/hieu luc) con bam schema cu (repo_hieu_luc + 5 ham hieu luc da bi 003 drop).
    # shortcut: tat theo settings.ENABLE_TIER1 cho den khi port tier1 sang node/tac_dong.
    tier1_phat_hien: list[dict] = []
    if settings.ENABLE_TIER1:
        with ket_noi() as conn:
            ph = chay_tier1(conn, don_vi_list, ngay,
                            van_ban_me_ids=[], can_cu_tho=can_cu_tho or [],
                            cap_tai_lieu=cap_tai_lieu)
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
                tier1_phat_hien.append({
                    "don_vi_id": p.don_vi_id,
                    "loai_loi": p.loai_loi, "tin_cay": p.tin_cay,
                    "doan_du_thao": p.doan_du_thao or "",
                    "so_hieu": vb[0], "ten_van_ban": vb[1],
                    "trich_dan": p.can_cu.trich_dan if p.can_cu else "",
                    "giai_thich": p.giai_thich or "",
                    "de_xuat_sua": p.de_xuat_sua or "",
                })

    # Tier2: moi chunk -> hybrid toan DB -> LLM
    don_vi_can_xet = [dv for dv in don_vi_list if dv.cap in {"khoan", "diem", "doan"}]

    def _xu_ly(dv) -> tuple[Any, list[dict], dict]:
        text = _chunk_embed_text(dv)
        emb = emb_by_id.get(dv.id)
        with ket_noi() as c:
            # Over-fetch: nhieu chunk cung Khoan me se bi gop lai, nen lay du de
            # sau khu trung van con du top_k Khoan rieng biet.
            # Co embedding da luu luc upload -> dung lai; nguoc lai embed tu text.
            if emb is not None:
                rows = tim_hybrid(
                    c, text, emb, ngay=ngay, top_k=req.top_k * 4,
                    van_ban_ids=req.van_ban_me_ids,
                )
            else:
                rows = tim_hybrid_tu_text(
                    c, text, ngay=ngay, top_k=req.top_k * 4,
                    van_ban_ids=req.van_ban_me_ids,
                )
            if not rows:
                return dv, [], {}
            diem_rrf = {r["chunk_id"]: r["diem_rrf"] for r in rows}
            ung_vien = nap_khoan_ung_vien(
                c, [r["chunk_id"] for r in rows], diem_rrf,
            )[: req.top_k]
        dv_dict = {
            "id": dv.id, "so_dieu": dv.so_dieu, "so_khoan": dv.so_khoan,
            "diem": dv.diem, "tieu_de": dv.tieu_de, "noi_dung": dv.noi_dung,
        }
        kq_llm = _so_sanh_chunk(dv_dict, ung_vien, is_local=req.is_local)
        return dv, ung_vien, kq_llm

    def _chuan_hoa_trang_thai(tt: str) -> str:
        tt = (tt or "").strip().lower()
        if tt in {"vi_pham", "vipham", "vi pham"}:
            return "VI_PHAM"
        if tt in {"hop_le", "hople", "hop le", "phu_hop"}:
            return "HOP_LE"
        return "CHUA_XAC_DINH"

    tier2_kq: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.LLM_SONG_SONG) as pool:
        futs = {pool.submit(_xu_ly, dv): dv for dv in don_vi_can_xet}
        for fut in concurrent.futures.as_completed(futs):
            try:
                dv, ung_vien, kq_llm = fut.result()
            except Exception as exc:
                logger.exception("Chunk loi: %s", exc)
                continue
            # Khong co ung vien nao -> chua co can cu
            if not ung_vien:
                tier2_kq.append({
                    "don_vi_id": dv.id, "trang_thai": "CHUA_XAC_DINH",
                    "doan_du_thao": dv.noi_dung,
                    "so_hieu": "", "ten_van_ban": "", "trich_dan": "",
                    "giai_thich": "Khong tim thay quy pham phap luat lien quan de doi chieu.",
                    "de_xuat_sua": "", "tin_cay": 0.0,
                })
                continue
            trang_thai = _chuan_hoa_trang_thai(kq_llm.get("trang_thai", ""))
            cc = kq_llm.get("can_cu") or {}
            uv_map = {u["khoan_id"]: u for u in ung_vien}
            u = uv_map.get(cc.get("khoan_id")) or ung_vien[0]
            if trang_thai == "CHUA_XAC_DINH":
                tier2_kq.append({
                    "don_vi_id": dv.id, "trang_thai": "CHUA_XAC_DINH",
                    "doan_du_thao": dv.noi_dung,
                    "so_hieu": "", "ten_van_ban": "", "trich_dan": "",
                    "giai_thich": kq_llm.get("giai_thich")
                    or "Noi dung du thao chua co can cu phap ly tuong ung.",
                    "de_xuat_sua": "", "tin_cay": kq_llm.get("tin_cay", 0.0),
                })
            else:
                # VI_PHAM: dung snippet LLM chep (chi phan sai) neu hop le; nguoc lai nguyen van.
                snippet = (kq_llm.get("noi_dung_du_thao") or "").strip()
                doan = (snippet if trang_thai == "VI_PHAM"
                        and _la_snippet_hop_le(snippet, dv.noi_dung) else dv.noi_dung)
                tier2_kq.append({
                    "don_vi_id": dv.id, "trang_thai": trang_thai,
                    "doan_du_thao": doan,
                    "so_hieu": u.get("so_hieu", ""),
                    "ten_van_ban": u.get("ten_van_ban", ""),
                    "trich_dan": cc.get("trich_dan") or u.get("noi_dung", ""),
                    "giai_thich": kq_llm.get("giai_thich", ""),
                    "de_xuat_sua": kq_llm.get("de_xuat_sua", "")
                    if trang_thai == "VI_PHAM" else "",
                    "tin_cay": kq_llm.get("tin_cay", 0.0),
                    "tac_dong": u.get("tac_dong"),   # kem sua doi (neu co) de tra ra ket qua
                    "cc_vi_tri": _vi_tri_can_cu(u),  # vi tri can cu: Dieu X khoan Y
                })

    ngay_iso = date.today().isoformat()

    # Tier1 findings deu la VI_PHAM
    for k in tier1_phat_hien:
        k["trang_thai"] = "VI_PHAM"

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


def _chuan_so_sanh(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _la_snippet_hop_le(snippet: str, nguyen_van: str) -> bool:
    """Snippet LLM chep la 1 doan con THUC SU cua nguyen van (chep dung, ngan hon)."""
    ns, nf = _chuan_so_sanh(snippet), _chuan_so_sanh(nguyen_van)
    return bool(ns) and ns in nf and len(ns) < len(nf)


def _vi_tri_can_cu(u: dict) -> str:
    """Vi tri can cu phap ly: 'Chuong .. Dieu X khoan Y diem Z' tu ung vien khoan me."""
    parts = []
    if u.get("phan"):
        parts.append(u["phan"])
    if u.get("chuong"):
        parts.append(u["chuong"])
    if u.get("so_dieu"):
        parts.append(f"Điều {u['so_dieu']}")
    if u.get("so_khoan"):
        parts.append(f"khoản {u['so_khoan']}")
    if u.get("diem"):
        parts.append(f"điểm {u['diem']}")
    return " ".join(parts)


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
    src = _file_goc(req.tai_lieu_id)
    if src is not None and src.suffix.lower() == ".docx":
        out_dir = _OUTPUT_DIR / req.tai_lieu_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{src.stem}{_HAU_TO_TC}.docx"
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
    shutil.rmtree(_DRAFT_DIR, ignore_errors=True)
    shutil.rmtree(_OUTPUT_DIR, ignore_errors=True)
    return {"da_xoa": n}


@router.delete("/draft/{tai_lieu_id}")
def xoa_draft(tai_lieu_id: str) -> dict:
    """Xoa 1 du thao (du_thao + du_thao_node cascade) + file goc/track-change da luu."""
    with ket_noi() as conn:
        n = rt.xoa_du_thao(conn, tai_lieu_id)
        conn.commit()
    shutil.rmtree(_DRAFT_DIR / tai_lieu_id, ignore_errors=True)
    shutil.rmtree(_OUTPUT_DIR / tai_lieu_id, ignore_errors=True)
    if not n:
        raise HTTPException(404, f"tai_lieu_id '{tai_lieu_id}' khong ton tai")
    return {"tai_lieu_id": tai_lieu_id, "da_xoa": True}


@router.get("/audit/docx/{tai_lieu_id}")
def tai_file_track_changes(tai_lieu_id: str) -> FileResponse:
    """Tai file '<ten_goc>_track_changes.docx' da tao o POST /audit/docx (data/track_changes)."""
    folder = _OUTPUT_DIR / tai_lieu_id
    hits = sorted(folder.glob(f"*{_HAU_TO_TC}.docx")) if folder.is_dir() else []
    if not hits:
        raise HTTPException(404, "Chua co file track-changes. Goi POST /audit/docx truoc.")
    f = hits[0]
    return FileResponse(
        str(f), filename=f.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
