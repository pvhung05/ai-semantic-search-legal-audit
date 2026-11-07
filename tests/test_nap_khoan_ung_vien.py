"""Test leo cay tu leaf ve don vi Khoan/Dieu (duong_dan)."""
from app.doisanh.retrieval.can_cu import _unit_path, _dieu_path, _to_tien_paths


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
