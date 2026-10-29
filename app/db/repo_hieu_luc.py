"""Repository thi hanh lenh sua doi + tra hieu luc theo ngay."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from psycopg import Connection


def khoan_hieu_luc_tai(
    conn: Connection, van_ban_id: str, so_dieu: str,
    so_khoan: str, diem: str | None, ngay: date,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM khoan_hieu_luc_tai(%s,%s,%s,%s,%s)",
            (van_ban_id, so_dieu, so_khoan, diem, ngay),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        cols = [c.name for c in cur.description]
        return dict(zip(cols, row))


def dieu_hieu_luc_tai(
    conn: Connection, van_ban_id: str, so_dieu: str, ngay: date,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM dieu_hieu_luc_tai(%s,%s,%s)",
            (van_ban_id, so_dieu, ngay),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        cols = [c.name for c in cur.description]
        return dict(zip(cols, row))


def ban_hop_nhat(conn: Connection, van_ban_id: str, ngay: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ban_hop_nhat(%s,%s)", (van_ban_id, ngay))
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def van_ban_me_qua_do_thi(conn: Connection, van_ban_ids: list[str]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM van_ban_me_qua_do_thi(%s) ORDER BY buoc_sau, van_ban_id",
            (van_ban_ids,),
        )
        return [{"van_ban_id": r[0], "buoc_sau": r[1]} for r in cur.fetchall()]


def _tim_dieu_hien_tai(
    conn: Connection, van_ban_dich_id: str, so_dieu: str, ngay: date | None
) -> dict[str, Any] | None:
    """Tim Dieu dang con hieu luc trong van ban dich theo so_dieu."""
    ngay = ngay or date.today()
    return dieu_hieu_luc_tai(conn, van_ban_dich_id, so_dieu, ngay)


def _tim_khoan_hien_tai(
    conn: Connection, van_ban_dich_id: str, so_dieu: str,
    so_khoan: str, diem: str | None, ngay: date | None,
) -> dict[str, Any] | None:
    ngay = ngay or date.today()
    return khoan_hieu_luc_tai(conn, van_ban_dich_id, so_dieu, so_khoan, diem, ngay)


def thi_hanh_lenh(conn: Connection, lenh_id: int) -> dict[str, Any]:
    """Thi hanh mot lenh quan_he_van_ban trong 1 transaction. Idempotent."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, nguon_id, dich_id, loai, dich_so_dieu, dich_so_khoan, dich_diem,
                      vi_tri, ngay_hieu_luc, noi_dung_moi, cum_tu_cu, cum_tu_moi,
                      nguon_lenh, da_ap_dung
               FROM quan_he_van_ban WHERE id=%s FOR UPDATE""",
            (lenh_id,),
        )
        row = cur.fetchone()
    if row is None:
        return {"lenh_id": lenh_id, "trang_thai": "khong_ton_tai"}
    (
        _id, nguon_id, dich_id, loai, dich_so_dieu, dich_so_khoan, dich_diem,
        vi_tri, ngay_hl, noi_dung_moi, cum_cu, cum_moi, nguon_lenh, da_ap_dung,
    ) = row
    if da_ap_dung:
        return {"lenh_id": lenh_id, "trang_thai": "da_ap_dung"}

    ngay = ngay_hl or date.today()
    ket_qua: dict[str, Any] = {"lenh_id": lenh_id, "loai": loai}

    try:
        if loai == "sua_doi":
            ket_qua.update(_thi_hanh_sua_doi(conn, dich_id, dich_so_dieu, dich_so_khoan,
                                             dich_diem, ngay, noi_dung_moi, nguon_id))
        elif loai == "bo_sung":
            ket_qua.update(_thi_hanh_bo_sung(conn, dich_id, dich_so_dieu, dich_so_khoan,
                                             dich_diem, vi_tri, ngay, noi_dung_moi, nguon_id))
        elif loai == "bai_bo":
            ket_qua.update(_thi_hanh_bai_bo(conn, dich_id, dich_so_dieu, dich_so_khoan, dich_diem, ngay))
        elif loai == "thay_cum_tu":
            ket_qua.update(_thi_hanh_thay_cum_tu(conn, dich_id, cum_cu, cum_moi))
        else:
            ket_qua["trang_thai"] = "bo_qua_loai"

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE quan_he_van_ban SET da_ap_dung=true, loi_ap_dung=NULL WHERE id=%s",
                (lenh_id,),
            )
        ket_qua.setdefault("trang_thai", "ok")
    except LoiApDung as exc:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE quan_he_van_ban SET loi_ap_dung=%s WHERE id=%s",
                (str(exc), lenh_id),
            )
        ket_qua["trang_thai"] = "loi"
        ket_qua["loi"] = str(exc)
    return ket_qua


class LoiApDung(RuntimeError):
    pass


def _thi_hanh_sua_doi(
    conn: Connection, dich_id: str, so_dieu: str | None,
    so_khoan: str | None, diem: str | None, ngay: date,
    noi_dung_moi: str | None, nguon_sua_doi_id: str,
) -> dict[str, Any]:
    """Sua Khoan hoac ca Dieu: ban cu dong hieu_luc_den=ngay-1, tao ban moi id@ngay."""
    if not so_dieu:
        raise LoiApDung("thieu dich_so_dieu")
    ngay_het = ngay - timedelta(days=1)
    if so_khoan:
        cu = _tim_khoan_hien_tai(conn, dich_id, so_dieu, so_khoan, diem, ngay - timedelta(days=1))
        if cu is None:
            raise LoiApDung(f"khong tim thay Khoan dich {so_dieu}:{so_khoan}")
        moi_id = f"{cu['id']}@{ngay.isoformat()}"
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE khoan SET hieu_luc_den=%s, trang_thai='het_hieu_luc', thay_boi_id=%s "
                "WHERE id=%s", (ngay_het, moi_id, cu["id"]),
            )
            cur.execute(
                """INSERT INTO khoan (id, dieu_id, van_ban_id, so_khoan, diem, parent_id,
                                      noi_dung, thu_tu, trang_thai, hieu_luc_tu,
                                      nguon_sua_doi_id, tin_cay)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'con_hieu_luc',%s,%s,'can_ra_soat')
                   ON CONFLICT (id) DO NOTHING""",
                (moi_id, cu["dieu_id"], cu["van_ban_id"], so_khoan, diem,
                 cu.get("parent_id"), noi_dung_moi or cu["noi_dung"], cu["thu_tu"],
                 ngay, nguon_sua_doi_id),
            )
        return {"trang_thai": "ok", "khoan_cu": cu["id"], "khoan_moi": moi_id}
    cu = _tim_dieu_hien_tai(conn, dich_id, so_dieu, ngay - timedelta(days=1))
    if cu is None:
        raise LoiApDung(f"khong tim thay Dieu dich {so_dieu}")
    moi_id = f"{cu['id']}@{ngay.isoformat()}"
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dieu_luat SET hieu_luc_den=%s, trang_thai='het_hieu_luc', thay_boi_id=%s "
            "WHERE id=%s", (ngay_het, moi_id, cu["id"]),
        )
        cur.execute(
            """INSERT INTO dieu_luat (id, van_ban_id, so_dieu, so_dieu_num, tieu_de,
                                       noi_dung, thu_tu, trang_thai, hieu_luc_tu,
                                       nguon_sua_doi_id, tin_cay)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'con_hieu_luc',%s,%s,'can_ra_soat')
               ON CONFLICT (id) DO NOTHING""",
            (moi_id, cu["van_ban_id"], so_dieu, cu["so_dieu_num"], cu["tieu_de"],
             noi_dung_moi or cu["noi_dung"], cu["thu_tu"], ngay, nguon_sua_doi_id),
        )
    return {"trang_thai": "ok", "dieu_cu": cu["id"], "dieu_moi": moi_id}


def _thi_hanh_bo_sung(
    conn: Connection, dich_id: str, so_dieu: str | None,
    so_khoan: str | None, diem: str | None, vi_tri: str | None,
    ngay: date, noi_dung_moi: str | None, nguon_sua_doi_id: str,
) -> dict[str, Any]:
    """Bo sung Khoan/Diem/Dieu moi. Danh lai thu_tu don gian (append)."""
    if not so_dieu:
        raise LoiApDung("thieu dich_so_dieu")
    moi_id = f"{dich_id}:D{so_dieu}"
    if so_khoan:
        moi_id = f"{moi_id}:K{so_khoan}"
        if diem:
            moi_id = f"{moi_id}:D{diem}"
        moi_id = f"{moi_id}@{ngay.isoformat()}"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM dieu_luat WHERE van_ban_id=%s AND so_dieu=%s "
                "ORDER BY hieu_luc_tu DESC NULLS LAST LIMIT 1",
                (dich_id, so_dieu),
            )
            row = cur.fetchone()
            if row is None:
                raise LoiApDung(f"khong co Dieu me {so_dieu} de bo sung Khoan")
            dieu_id_me = row[0]
            cur.execute(
                "SELECT COALESCE(MAX(thu_tu),0)+1 FROM khoan WHERE dieu_id=%s",
                (dieu_id_me,),
            )
            thu_tu = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO khoan (id, dieu_id, van_ban_id, so_khoan, diem,
                                      noi_dung, thu_tu, trang_thai, hieu_luc_tu,
                                      nguon_sua_doi_id, tin_cay)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'con_hieu_luc',%s,%s,'can_ra_soat')
                   ON CONFLICT (id) DO NOTHING""",
                (moi_id, dieu_id_me, dich_id, so_khoan, diem,
                 noi_dung_moi or "", thu_tu, ngay, nguon_sua_doi_id),
            )
        return {"trang_thai": "ok", "khoan_moi": moi_id}
    moi_id = f"{moi_id}@{ngay.isoformat()}"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(thu_tu),0)+1 FROM dieu_luat WHERE van_ban_id=%s",
            (dich_id,),
        )
        thu_tu = cur.fetchone()[0]
        from app.ingestion.parser import _so_dieu_num  # noqa: E402
        cur.execute(
            """INSERT INTO dieu_luat (id, van_ban_id, so_dieu, so_dieu_num,
                                       noi_dung, thu_tu, trang_thai, hieu_luc_tu,
                                       nguon_sua_doi_id, tin_cay)
               VALUES (%s,%s,%s,%s,%s,%s,'con_hieu_luc',%s,%s,'can_ra_soat')
               ON CONFLICT (id) DO NOTHING""",
            (moi_id, dich_id, so_dieu, _so_dieu_num(so_dieu),
             noi_dung_moi or "", thu_tu, ngay, nguon_sua_doi_id),
        )
    return {"trang_thai": "ok", "dieu_moi": moi_id}


def _thi_hanh_bai_bo(
    conn: Connection, dich_id: str, so_dieu: str | None,
    so_khoan: str | None, diem: str | None, ngay: date,
) -> dict[str, Any]:
    if not so_dieu:
        raise LoiApDung("thieu dich_so_dieu")
    if so_khoan:
        cu = _tim_khoan_hien_tai(conn, dich_id, so_dieu, so_khoan, diem, ngay - timedelta(days=1))
        if cu is None:
            raise LoiApDung(f"khong co Khoan {so_dieu}:{so_khoan} de bai bo")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE khoan SET trang_thai='bai_bo', hieu_luc_den=%s WHERE id=%s",
                (ngay - timedelta(days=1), cu["id"]),
            )
        return {"trang_thai": "ok", "khoan": cu["id"]}
    cu = _tim_dieu_hien_tai(conn, dich_id, so_dieu, ngay - timedelta(days=1))
    if cu is None:
        raise LoiApDung(f"khong co Dieu {so_dieu} de bai bo")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dieu_luat SET trang_thai='bai_bo', hieu_luc_den=%s WHERE id=%s",
            (ngay - timedelta(days=1), cu["id"]),
        )
    return {"trang_thai": "ok", "dieu": cu["id"]}


def _thi_hanh_thay_cum_tu(
    conn: Connection, dich_id: str, cum_cu: str | None, cum_moi: str | None,
) -> dict[str, Any]:
    if not cum_cu:
        raise LoiApDung("thieu cum_tu_cu")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE khoan SET noi_dung = REPLACE(noi_dung, %s, %s) "
            "WHERE van_ban_id=%s AND noi_dung LIKE %s",
            (cum_cu, cum_moi or "", dich_id, f"%{cum_cu}%"),
        )
        so_dong = cur.rowcount
    return {"trang_thai": "ok", "so_khoan_cap_nhat": so_dong}


def cap_nhat_trang_thai_van_ban(conn: Connection, van_ban_id: str) -> str:
    """Cap nhat van_ban.trang_thai tu view van_ban_trang_thai_tinh."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT trang_thai_tinh FROM van_ban_trang_thai_tinh WHERE id=%s",
            (van_ban_id,),
        )
        row = cur.fetchone()
        if row is None:
            return ""
        tt = row[0]
        cur.execute(
            "UPDATE van_ban SET trang_thai=%s WHERE id=%s",
            (tt, van_ban_id),
        )
    return tt


def thi_hanh_lenh_chua_ap_dung(conn: Connection) -> list[dict[str, Any]]:
    """Thi hanh tat ca lenh da_ap_dung=false. Idempotent."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, dich_id FROM quan_he_van_ban WHERE da_ap_dung=false ORDER BY id")
        rows = cur.fetchall()
    ket_qua: list[dict[str, Any]] = []
    van_ban_dich_set: set[str] = set()
    for lid, dich_id in rows:
        kq = thi_hanh_lenh(conn, lid)
        ket_qua.append(kq)
        if dich_id:
            van_ban_dich_set.add(dich_id)
        conn.commit()
    for vb in van_ban_dich_set:
        cap_nhat_trang_thai_van_ban(conn, vb)
    conn.commit()
    return ket_qua
