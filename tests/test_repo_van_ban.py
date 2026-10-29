"""Smoke test cho repo_van_ban: upsert idempotent + get_muc_luc.

Danh dau @pytest.mark.integration vi can DB that.
"""
from datetime import date

import pytest

from app.db import repo_van_ban as repo
from app.db.session import ket_noi
from app.models.schemas import Dieu, Khoan, VanBanMeta, VanBanParsed


@pytest.fixture
def van_ban_mau() -> VanBanParsed:
    meta = VanBanMeta(
        id="TEST-VB-001", so_hieu="TEST-001/2026", ten="Van ban test",
        loai="thong_tu", cap=7,
    )
    d1 = Dieu(
        so_dieu="1", so_dieu_num=1, tieu_de="Pham vi",
        noi_dung="Thong tu nay quy dinh ...", thu_tu=1,
        khoan=[
            Khoan(so_khoan="1", noi_dung="Khoan 1", thu_tu=1),
            Khoan(so_khoan="2", noi_dung="Khoan 2", thu_tu=2),
            Khoan(so_khoan="2", diem="a", noi_dung="Diem a", thu_tu=3, parent_so_khoan="2"),
        ],
    )
    return VanBanParsed(meta=meta, dieu=[d1])


@pytest.mark.integration
def test_upsert_idempotent(van_ban_mau: VanBanParsed) -> None:
    with ket_noi() as conn:
        try:
            s1 = repo.luu_van_ban_day_du(conn, van_ban_mau)
            s2 = repo.luu_van_ban_day_du(conn, van_ban_mau)
            conn.commit()
            assert s1 == s2 == {"so_dieu": 1, "so_khoan": 3}
            muc = repo.get_muc_luc(conn, "TEST-VB-001", date.today())
            assert len(muc) == 1 and muc[0]["so_dieu"] == "1"
            full = repo.get_dieu_full(conn, "TEST-VB-001:D1")
            assert full is not None and len(full["khoan"]) == 3
        finally:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM van_ban WHERE id=%s", ("TEST-VB-001",))
            conn.commit()
