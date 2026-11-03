"""4 API gon: /ask, /upload/legal, /upload/draft, /audit."""
from __future__ import annotations

import concurrent.futures
import json
import logging
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

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
from app.doisanh.qa.chat import hoi_dap
from app.doisanh.retrieval.hybrid import tim_hybrid_tu_text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["simple"])


# ============================================================
# 1) /ask
# ============================================================
class AskRequest(BaseModel):
    cau_hoi: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(8, ge=1, le=20)
    is_local: Optional[bool] = Field(
        None, description="None=theo .env; true=Qwen local; false=Gemini",
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
    with ket_noi() as conn, conn.cursor() as cur:
        if con_hieu_luc:
            cur.execute(
                """SELECT v.id, v.so_hieu, v.ten, v.loai, v.cap, v.linh_vuc,
                          v.ngay_hieu_luc, v.ngay_het_hieu_luc,
                          (SELECT COUNT(*) FROM khoan k
                           WHERE k.van_ban_id=v.id AND k.trang_thai<>'bai_bo') AS so_khoan
                   FROM van_ban v
                   WHERE (v.ngay_het_hieu_luc IS NULL OR v.ngay_het_hieu_luc > %s)
                     AND (v.ngay_hieu_luc IS NULL OR v.ngay_hieu_luc <= %s)
                   ORDER BY v.cap, v.so_hieu""",
                (ngay, ngay),
            )
        else:
            cur.execute(
                """SELECT v.id, v.so_hieu, v.ten, v.loai, v.cap, v.linh_vuc,
                          v.ngay_hieu_luc, v.ngay_het_hieu_luc,
                          (SELECT COUNT(*) FROM khoan k
                           WHERE k.van_ban_id=v.id AND k.trang_thai<>'bai_bo') AS so_khoan
                   FROM van_ban v ORDER BY v.cap, v.so_hieu""",
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
        text = doc_file(tmp_path)
        tai_lieu_id = rt.sinh_id_tai_lieu()
        file_hash = rt.hash_file(tmp_path)
        storage_key = rt.luu_file(tmp_path, tai_lieu_id)
        seg = segment_du_thao(text, tai_lieu_id)
        with ket_noi() as conn:
            rt.tao_tai_lieu(
                conn, tai_lieu_id,
                ten=file.filename or tai_lieu_id,
                loai="khac", cap_tuong_duong=None,
                ngay_du_kien=date.today(),
                linh_vuc=[],
                can_cu_tho=seg.can_cu_tho,
                co_cau_truc_dieu=seg.co_cau_truc_dieu,
                storage_key=storage_key, file_hash=file_hash,
            )
            for dv in seg.don_vi:
                rt.luu_don_vi(conn, {
                    "id": dv.id, "tai_lieu_id": tai_lieu_id, "parent_id": dv.parent_id,
                    "cap": dv.cap, "so_dieu": dv.so_dieu, "so_khoan": dv.so_khoan,
                    "diem": dv.diem, "tieu_de": dv.tieu_de,
                    "noi_dung": dv.noi_dung, "hash": dv.hash, "thu_tu": dv.thu_tu,
                })
            conn.commit()
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
        None, description="None=theo .env; true=Qwen local; false=Gemini",
    )


def _loai_rang_buoc(text: str) -> list[str]:
    """Nhan dien loai rang buoc so lieu trong Khoan me bang keyword (rule, truoc LLM).

    - san: muc toi thieu (du thao thap hon -> vi pham)
    - tran: muc toi da (du thao cao hon -> vi pham)
    - co_dinh: con so co dinh (du thao khac -> vi pham)
    - trao_quyen: luat trao quyen tu quyet/thoa thuan (du thao chon muc cu the -> hop le)
    """
    t = (text or "").lower()
    kq: list[str] = []
    if any(k in t for k in ("ít nhất", "tối thiểu", "không thấp hơn", "không ít hơn", "không dưới")):
        kq.append("san")
    if any(k in t for k in ("không quá", "tối đa", "không vượt quá", "không được quá",
                            "không nhiều hơn", "không cao hơn")):
        kq.append("tran")
    if any(k in t for k in ("do ", "có thể thỏa thuận", "theo thỏa thuận",
                            "hai bên thỏa thuận", "tự quyết định", "do các bên")):
        kq.append("trao_quyen")
    return kq or ["khong_ro"]


def _nap_khoan_ung_vien(conn, chunk_ids: list[str], diem_rrf: dict[str, float]) -> list[dict]:
    """Gom cac chunk ve don vi me (Khoan me, hoac Dieu neu khong chia Khoan),
    khu trung, dung lai NGUYEN Khoan (cau dan + moi diem a/b/c/d) de LLM doc du ngu canh.
    diem_rrf cua moi don vi = max cua cac chunk thanh phan.
    """
    if not chunk_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.id, c.khoan_id, c.dieu_id, k.parent_id, k.diem,
                      v.id, v.so_hieu, v.ten, d.so_dieu, d.tieu_de, d.noi_dung
               FROM chunk c
               JOIN van_ban v ON v.id = c.van_ban_id
               LEFT JOIN dieu_luat d ON d.id = c.dieu_id
               LEFT JOIN khoan k ON k.id = c.khoan_id
               WHERE c.id = ANY(%s)""",
            (chunk_ids,),
        )
        rows = cur.fetchall()

    # Gom theo don vi me: neu chunk la Diem -> Khoan me (parent_id); neu Khoan -> chinh no;
    # neu Dieu khong Khoan -> Dieu.
    units: dict[str, dict] = {}
    khoan_me_ids: set[str] = set()
    for (cid, kid, did, parent_id, diem, vb_id, so_hieu, ten_vb,
         so_dieu, tieu_de_dieu, dieu_nd) in rows:
        rrf = diem_rrf.get(cid, 0.0)
        if kid:
            unit_id = parent_id or kid
            kind = "khoan"
            khoan_me_ids.add(unit_id)
        else:
            unit_id = did or cid
            kind = "dieu"
        u = units.get(unit_id)
        if u is None:
            units[unit_id] = {
                "unit_id": unit_id, "kind": kind, "van_ban_id": vb_id,
                "so_hieu": so_hieu, "ten_van_ban": ten_vb,
                "so_dieu": so_dieu, "tieu_de_dieu": tieu_de_dieu,
                "dieu_noi_dung": dieu_nd, "diem_rrf": rrf,
            }
        elif rrf > u["diem_rrf"]:
            u["diem_rrf"] = rrf

    # Dung lai noi_dung day du cho tung Khoan me: cau dan + tat ca diem con.
    noi_dung_khoan: dict[str, tuple[str | None, str]] = {}
    if khoan_me_ids:
        ids = list(khoan_me_ids)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, so_khoan, diem, noi_dung, thu_tu, parent_id
                   FROM khoan
                   WHERE id = ANY(%s) OR parent_id = ANY(%s)
                   ORDER BY thu_tu""",
                (ids, ids),
            )
            krows = cur.fetchall()
        lead: dict[str, tuple[str | None, str]] = {}
        con: dict[str, list[tuple[str | None, str]]] = {}
        for kid, so_khoan, diem, nd, tt, parent_id in krows:
            if kid in khoan_me_ids and diem is None:
                lead[kid] = (so_khoan, nd or "")
            if parent_id in khoan_me_ids:
                con.setdefault(parent_id, []).append((diem, nd or ""))
        for kmid in khoan_me_ids:
            so_khoan, lead_nd = lead.get(kmid, (None, ""))
            parts = [lead_nd] if lead_nd else []
            for diem, nd in con.get(kmid, []):
                parts.append(f"{diem}) {nd}" if diem else nd)
            noi_dung_khoan[kmid] = (so_khoan, "\n".join(p for p in parts if p).strip())

    out = []
    for unit_id, u in units.items():
        if u["kind"] == "khoan":
            so_khoan, noi_dung = noi_dung_khoan.get(unit_id, (None, ""))
        else:
            so_khoan, noi_dung = None, (u["dieu_noi_dung"] or "").strip()
        out.append({
            "khoan_id": unit_id,
            "van_ban_id": u["van_ban_id"],
            "so_hieu": u["so_hieu"], "ten_van_ban": u["ten_van_ban"],
            "so_dieu": u["so_dieu"], "tieu_de_dieu": u["tieu_de_dieu"],
            "so_khoan": so_khoan, "diem": None,
            "noi_dung": noi_dung,
            "loai_rang_buoc": _loai_rang_buoc(noi_dung),
            "diem_rrf": u["diem_rrf"],
        })
    out.sort(key=lambda x: -x["diem_rrf"])
    return out


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
            "so_dieu": u["so_dieu"], "so_khoan": u["so_khoan"], "diem": u["diem"],
            "tieu_de_dieu": u["tieu_de_dieu"],
            "loai_rang_buoc": u.get("loai_rang_buoc", ["khong_ro"]),
            "noi_dung": u["noi_dung"][:1500],
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
    with ket_noi() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, can_cu_tho, cap_tuong_duong FROM tai_lieu WHERE id=%s",
            (req.tai_lieu_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(404, f"tai_lieu_id '{req.tai_lieu_id}' khong ton tai")
    _, can_cu_tho, cap_tai_lieu = row

    # Nap don vi tu DB
    with ket_noi() as conn:
        rows = rt.danh_sach_don_vi(conn, req.tai_lieu_id)
    from app.doisanh.audit.segment import DonViSegment
    don_vi_list = [DonViSegment(
        id=r["id"], cap=r["cap"], so_dieu=r["so_dieu"], so_khoan=r["so_khoan"],
        diem=r["diem"], tieu_de=r["tieu_de"], noi_dung=r["noi_dung"],
        hash=r["hash"], thu_tu=r["thu_tu"], parent_id=r["parent_id"],
    ) for r in rows]
    if not don_vi_list:
        raise HTTPException(422, "Du thao chua co don vi nao, hay upload lai")

    # Tier1: can cu het hieu luc, dan chieu sai, trich sai nguyen van.
    tier1_phat_hien: list[dict] = []
    with ket_noi() as conn:
        ph = chay_tier1(conn, don_vi_list, ngay,
                        van_ban_me_ids=[], can_cu_tho=can_cu_tho or [],
                        cap_tai_lieu=cap_tai_lieu)
        # map ten VB can cu
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

    def _xu_ly(dv: DonViSegment) -> tuple[DonViSegment, list[dict], dict]:
        text = _chunk_embed_text(dv)
        with ket_noi() as c:
            # Over-fetch: nhieu chunk cung Khoan me se bi gop lai, nen lay du de
            # sau khu trung van con du top_k Khoan rieng biet.
            rows = tim_hybrid_tu_text(
                c, text, ngay=ngay, top_k=req.top_k * 4,
                van_ban_ids=req.van_ban_me_ids,
            )
            if not rows:
                return dv, [], {}
            diem_rrf = {r["chunk_id"]: r["diem_rrf"] for r in rows}
            ung_vien = _nap_khoan_ung_vien(
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
                tier2_kq.append({
                    "don_vi_id": dv.id, "trang_thai": trang_thai,
                    "doan_du_thao": dv.noi_dung,
                    "so_hieu": u.get("so_hieu", ""),
                    "ten_van_ban": u.get("ten_van_ban", ""),
                    "trich_dan": cc.get("trich_dan") or u.get("noi_dung", ""),
                    "giai_thich": kq_llm.get("giai_thich", ""),
                    "de_xuat_sua": kq_llm.get("de_xuat_sua", "")
                    if trang_thai == "VI_PHAM" else "",
                    "tin_cay": kq_llm.get("tin_cay", 0.0),
                })

    # Lay vi tri du thao
    dv_vi_tri = {dv.id: _vi_tri(dv) for dv in don_vi_list}

    # Tier1 findings deu la VI_PHAM
    for k in tier1_phat_hien:
        k["trang_thai"] = "VI_PHAM"

    nhom: dict[str, list[dict]] = {"VI_PHAM": [], "HOP_LE": [], "CHUA_XAC_DINH": []}
    for k in tier1_phat_hien + tier2_kq:
        tag = k.get("trang_thai", "CHUA_XAC_DINH")
        nhom[tag].append({
            "don_vi_id": k["don_vi_id"],
            "vi_tri_du_thao": dv_vi_tri.get(k["don_vi_id"], k["don_vi_id"]),
            "noi_dung_du_thao": k.get("doan_du_thao", ""),
            "can_cu_phap_ly": {
                "so_hieu": k.get("so_hieu", ""),
                "ten_van_ban": k.get("ten_van_ban", ""),
                "trich_dan": k.get("trich_dan", ""),
            },
            "giai_thich": k.get("giai_thich", ""),
            "de_xuat_sua": k.get("de_xuat_sua", ""),
            "tin_cay": k.get("tin_cay", 0.0),
        })

    return {
        "tai_lieu_id": req.tai_lieu_id,
        "thong_ke": {k: len(v) for k, v in nhom.items()},
        "ket_qua": nhom,
    }


def _vi_tri(dv) -> str:
    pos = ""
    if dv.so_dieu: pos += f"Dieu {dv.so_dieu}"
    if dv.so_khoan: pos += f" Khoan {dv.so_khoan}"
    if dv.diem: pos += f" Diem {dv.diem}"
    return pos or f"Doan {dv.thu_tu}"
