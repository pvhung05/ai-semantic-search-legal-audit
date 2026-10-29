"""Anh xa Dieu du thao <-> Dieu van ban me qua LLM, cong them dan chieu."""
from __future__ import annotations

from typing import Callable

from psycopg import Connection

from app.audit.consolidate import muc_luc
from app.audit.prompts import prompt_mapping
from app.audit.segment import DonViSegment
from app.config import settings
from app.ingestion.citation_parser import trich_dan_chieu
from app.models.llm import goi_json


def _lay_muc_luc_du_thao(don_vi_list: list[DonViSegment]) -> list[dict]:
    return [
        {
            "id": dv.id, "so_dieu": dv.so_dieu or "",
            "tieu_de": dv.tieu_de or "",
            "mo_dau": (dv.noi_dung or "")[:200],
        }
        for dv in don_vi_list
        if dv.cap in {"dieu", "cum"}
    ]


def _lay_muc_luc_me(conn: Connection, van_ban_ids: list[str], ngay) -> list[dict]:
    rows: list[dict] = []
    with conn.cursor() as cur:
        for vb in van_ban_ids:
            cur.execute("SELECT so_hieu, ten FROM van_ban WHERE id=%s", (vb,))
            r = cur.fetchone()
            ten_vb = r[1] if r else vb
            so_hieu = r[0] if r else ""
            ml = muc_luc(conn, vb, ngay)
            for item in ml:
                rows.append({
                    "dieu_id": item["dieu_id"],
                    "ten_vb": ten_vb, "so_hieu": so_hieu,
                    "so_dieu": item["so_dieu"],
                    "tieu_de": item["tieu_de"],
                    "tom_tat": item["tom_tat"],
                })
    return rows


def anh_xa_dieu(
    conn: Connection, don_vi_list: list[DonViSegment], van_ban_me_ids: list[str],
    ngay, goi_json_fn: Callable[..., object] = goi_json,
    max_dieu_me: int | None = None,
) -> list[dict]:
    """Tra: [{don_vi_id, dieu_me_ids:[], loai, tin_cay, nguon}]."""
    max_dm = max_dieu_me or settings.AUDIT_MAX_DIEU_ME
    muc_du_thao = _lay_muc_luc_du_thao(don_vi_list)
    muc_me = _lay_muc_luc_me(conn, van_ban_me_ids, ngay)
    me_id_set = {m["dieu_id"] for m in muc_me}

    data = goi_json_fn(prompt_mapping(muc_du_thao, muc_me, max_dm))
    if not isinstance(data, list):
        if isinstance(data, dict):
            for k in ("items", "anh_xa", "ket_qua", "data", "mapping"):
                if isinstance(data.get(k), list):
                    data = data[k]
                    break
            else:
                data = []
        else:
            data = []

    don_vi_id_set = {dv["id"] for dv in muc_du_thao}
    valid: list[dict] = []
    anh_xa_dict: dict[str, dict] = {}

    for item in data:
        don_vi_id = item.get("don_vi_id")
        if don_vi_id not in don_vi_id_set:
            continue
        dieu_me_ids = [x for x in (item.get("dieu_me_ids") or []) if x in me_id_set][:max_dm]
        loai = item.get("loai") or "khong"
        if loai not in {"cu_the_hoa", "dan_chieu", "cung_chu_de", "khong"}:
            loai = "khong"
        tin_cay = float(item.get("tin_cay") or 0.5)
        rec = {"don_vi_id": don_vi_id, "dieu_me_ids": dieu_me_ids,
               "loai": loai, "tin_cay": tin_cay, "nguon": "llm"}
        anh_xa_dict[don_vi_id] = rec
        valid.append(rec)

    # Bo sung anh_xa 'dan_chieu' tu text du thao -> Dieu me dan thang
    van_ban_me_set = set(van_ban_me_ids)
    with conn.cursor() as cur:
        for dv in don_vi_list:
            if dv.cap not in {"dieu", "cum"}:
                continue
            dcs = trich_dan_chieu(dv.noi_dung or "")
            dieu_me_them: list[str] = []
            for dc in dcs:
                if dc.la_noi_bo or not dc.so_hieu:
                    continue
                cur.execute("SELECT id FROM van_ban WHERE so_hieu=%s", (dc.so_hieu,))
                r = cur.fetchone()
                if not r or r[0] not in van_ban_me_set:
                    continue
                if dc.so_dieu is None:
                    continue
                cur.execute(
                    "SELECT id FROM dieu_luat WHERE van_ban_id=%s AND so_dieu=%s "
                    "AND (hieu_luc_den IS NULL) ORDER BY hieu_luc_tu DESC NULLS LAST LIMIT 1",
                    (r[0], dc.so_dieu),
                )
                r2 = cur.fetchone()
                if r2:
                    dieu_me_them.append(r2[0])
            if not dieu_me_them:
                continue
            rec = anh_xa_dict.get(dv.id)
            if rec is None:
                rec = {"don_vi_id": dv.id, "dieu_me_ids": [],
                       "loai": "dan_chieu", "tin_cay": 1.0, "nguon": "dan_chieu"}
                anh_xa_dict[dv.id] = rec
                valid.append(rec)
            for d in dieu_me_them:
                if d not in rec["dieu_me_ids"] and len(rec["dieu_me_ids"]) < max_dm:
                    rec["dieu_me_ids"].append(d)
    return valid
