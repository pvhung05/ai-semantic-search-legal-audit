from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.doisanh.audit.prompts import prompt_tier2_de_xuat, prompt_tier2_khoan
from app.doisanh.audit.segment import DonViSegment
from app.doisanh.audit.so_sanh import chay_tier2, de_xuat_sua_chunk, so_sanh_chunk


def test_prompt_tier2_de_xuat():
    doan = {"noi_dung": "Thoi han xu ly la 30 ngay."}
    can_cu = {
        "so_hieu": "01/2024/QH15",
        "ten_van_ban": "Luat A",
        "so_dieu": 5,
        "so_khoan": 1,
        "diem": None,
        "tieu_de_dieu": "Thoi han",
        "noi_dung": "Thoi han khong qua 10 ngay.",
    }
    messages = prompt_tier2_de_xuat(doan, can_cu, snippet_sai="30 ngay", ly_do_so_bo="vuot tran", trich_yeu="Luat Test")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "chuyen gia phap che" in messages[0]["content"].lower() or "chuyên gia pháp chế" in messages[0]["content"].lower()
    assert "30 ngay" in messages[1]["content"]
    assert "01/2024/QH15" in messages[1]["content"]


def test_so_sanh_chunk_pass1_defaults_to_think_false():
    dv = {"id": "d1", "noi_dung": "Noi dung test"}
    uv = [{"khoan_id": "k1", "so_hieu": "01/2020", "so_dieu": 1, "so_khoan": 1, "diem": None, "tieu_de_dieu": "T", "noi_dung": "N"}]
    with patch("app.doisanh.audit.so_sanh.goi_json") as mock_goi:
        mock_goi.return_value = {"trang_thai": "hop_le"}
        res = so_sanh_chunk(dv, uv)
        assert res["trang_thai"] == "hop_le"
        mock_goi.assert_called_once()
        assert mock_goi.call_args.kwargs["think"] is False


def test_de_xuat_sua_chunk_pass2_defaults_to_think_true():
    dv = {"id": "d1", "noi_dung": "Noi dung test 30 ngay"}
    cc = {"khoan_id": "k1", "so_hieu": "01/2020", "noi_dung": "Toi da 10 ngay"}
    with patch("app.doisanh.audit.so_sanh.goi_json") as mock_goi:
        mock_goi.return_value = {"giai_thich": "Vuot tran 10 ngay", "de_xuat_sua": "10 ngay"}
        res = de_xuat_sua_chunk(dv, cc, snippet_sai="30 ngay")
        assert res["de_xuat_sua"] == "10 ngay"
        mock_goi.assert_called_once()
        assert mock_goi.call_args.kwargs["think"] is True


def test_chay_tier2_cascade_workflow():
    dv = DonViSegment(
        id="d1", cap="khoan", so_dieu=1, so_khoan=1, diem=None,
        tieu_de=None, noi_dung="Thoi han la 30 ngay lam viec.",
        hash="h", thu_tu=1, parent_id=None,
    )
    ung_vien = [{
        "chunk_id": "c1", "khoan_id": "k1", "so_hieu": "01/2024/QH15",
        "ten_van_ban": "Luat Mau", "so_dieu": 2, "so_khoan": 1, "diem": None,
        "tieu_de_dieu": "Thoi han", "loai_rang_buoc": ["tran"],
        "noi_dung": "Thoi han khong qua 10 ngay lam viec.", "tac_dong": None,
    }]

    # Mock DB retrieval
    with patch("app.doisanh.audit.so_sanh.ket_noi"), \
         patch("app.doisanh.audit.so_sanh.tim_hybrid_tu_text", return_value=[{"chunk_id": "c1", "diem_rrf": 1.0}]), \
         patch("app.doisanh.audit.so_sanh.nap_khoan_ung_vien", return_value=ung_vien), \
         patch("app.doisanh.audit.so_sanh.goi_json") as mock_goi:

        # Lan 1 tra ve vi_pham, Lan 2 tra ve de xuat sua
        mock_goi.side_effect = [
            {"trang_thai": "vi_pham", "can_cu": {"khoan_id": "k1"}, "noi_dung_du_thao": "30 ngay", "giai_thich": "so bo"},
            {"giai_thich": "Vuot tran 10 ngay", "de_xuat_sua": "10 ngay"},
        ]

        from datetime import date
        kq = chay_tier2([dv], {}, trich_yeu="Test", ngay=date(2026, 1, 1), van_ban_me_ids=None, is_local=True)

        assert len(kq) == 1
        item = kq[0]
        assert item["trang_thai"] == "VI_PHAM"
        assert item["de_xuat_sua"] == "10 ngay"
        assert item["giai_thich"] == "Vuot tran 10 ngay"
        assert mock_goi.call_count == 2
        # Call 1 la Pass 1 (think=False), Call 2 la Pass 2 (think=True)
        assert mock_goi.call_args_list[0].kwargs["think"] is False
        assert mock_goi.call_args_list[1].kwargs["think"] is True
