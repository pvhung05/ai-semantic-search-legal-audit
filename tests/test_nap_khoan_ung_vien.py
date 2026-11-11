"""Test leo cay tu leaf ve don vi Khoan/Dieu (duong_dan)."""
from app.doisanh.retrieval.can_cu import (
    _dieu_path, _gop_anh_em, _noi_khong_lap, _to_tien_paths, _unit_path,
)


def test_noi_khong_lap_bo_khoan_da_nam_trong_dieu():
    dieu = "Điều 19. Nơi tổ chức\n1. Khoản một.\n2. Khoản  hai."
    assert _noi_khong_lap([None, dieu, "1. Khoản một.", "2. Khoản hai."]) == dieu


def test_noi_khong_lap_giu_con_khi_cha_chua_chua():
    assert _noi_khong_lap(["Tên điều", "1. Khoản", "a) điểm"]) == "Tên điều\n1. Khoản\na) điểm"


def _p(*paths):
    return {p: {"vb": "V", "rank": i, "rrf": 0.0} for i, p in enumerate(paths)}


def test_gop_diem_le_giu_nguyen():
    assert set(_gop_anh_em(_p("CI>D5>K1>da"))) == {"CI>D5>K1>da"}  # 1 diem le -> khong leo len cha


def test_gop_nhieu_diem_cung_khoan_len_khoan():
    assert set(_gop_anh_em(_p("CI>D5>K1>da", "CI>D5>K1>db"))) == {"CI>D5>K1"}


def test_gop_nhieu_khoan_cung_dieu_len_dieu():
    assert set(_gop_anh_em(_p("CI>D5>K1", "CI>D5>K2"))) == {"CI>D5"}


def test_gop_cascade_diem_khoan_dieu():
    # 2 diem cung K1 -> K1; K1 + K2 cung D5 -> D5
    assert set(_gop_anh_em(_p("CI>D5>K1>da", "CI>D5>K1>db", "CI>D5>K2"))) == {"CI>D5"}


def test_gop_dieu_anh_em_khong_leo_len_chuong():
    assert set(_gop_anh_em(_p("CI>D5", "CI>D6"))) == {"CI>D5", "CI>D6"}  # cha la Chuong -> giu nguyen


def test_gop_diem_khac_khoan_giu_rieng():
    kq = set(_gop_anh_em(_p("CI>D5>K1>da", "CI>D5>K2>db")))  # moi khoan 1 diem -> khong gop
    assert kq == {"CI>D5>K1>da", "CI>D5>K2>db"}


def test_to_tien_paths():
    assert _to_tien_paths("P1>CIV>D48>K1") == ["P1", "P1>CIV", "P1>CIV>D48", "P1>CIV>D48>K1"]
    assert _to_tien_paths("CI>D5") == ["CI", "CI>D5"]
    assert _to_tien_paths("") == []


def test_diem_leo_ve_khoan():
    assert _unit_path("CXI>M3>D154>K8>da") == "CXI>M3>D154>K8"


def test_khoan_giu_nguyen():
    assert _unit_path("CI>D5>K2") == "CI>D5>K2"


def test_dieu_khong_khoan_dung_ca_dieu():
    assert _unit_path("CI>D5") == "CI>D5"


def test_dieu_path():
    assert _dieu_path("CXI>M3>D154>K8") == "CXI>M3>D154"
    assert _dieu_path("CI>D5") == "CI>D5"
    assert _dieu_path("CI>M1") is None  # khong co Dieu
