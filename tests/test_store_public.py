"""Test cac ham thuan cua store_public: map trang thai, parse ngay/so thu tu, flatten cay.

Chi kiem logic parse/mapping (co che), khong khang dinh noi dung phap ly.
"""
from datetime import date

from app.crawl_vbpl import store_public as sp


def test_map_trang_thai():
    assert sp._map_trang_thai("HET_HIEU_LUC") == "het_hieu_luc"
    assert sp._map_trang_thai("Het_Hieu_Luc_Mot_Phan") == "het_hieu_luc_mot_phan"
    assert sp._map_trang_thai("TAM_NGUNG") == "khong_xac_dinh"  # khong co enum tuong ung
    assert sp._map_trang_thai(None) == "khong_xac_dinh"


def test_parse_date():
    assert sp._parse_date("2015-02-05T00:00:00") == date(2015, 2, 5)
    assert sp._parse_date("2026-01-01") == date(2026, 1, 1)
    assert sp._parse_date(None) is None
    assert sp._parse_date("") is None


def test_so_thu_tu_theo_cap():
    assert sp._so_thu_tu("dieu", {"content": {"title": "Điều 54"}}) == "54"
    assert sp._so_thu_tu("dieu", {"title": "Điều 5. Lựa chọn..."}) == "5"
    assert sp._so_thu_tu("chuong", {"title": "Chương I\nQUY ĐỊNH CHUNG"}) == "I"
    assert sp._so_thu_tu("khoan", {"title": "Khoản 2"}) == "2"
    assert sp._so_thu_tu("diem", {"title": "Điểm a"}) == "a"
    # fallback khi title la noi dung tho
    assert sp._so_thu_tu("khoan", {"title": "2. Doanh nghiệp..."}) == "2"
    assert sp._so_thu_tu("diem", {"title": "b) Trường hợp..."}) == "b"


def test_flatten_cay_giu_thu_tu_cha_truoc_con():
    tree = [{
        "id": "c1", "level": "Chapter", "title": "Chương I", "ptype": 2,
        "orderIndex": 1, "isLeaf": False, "content": {"title": "Chương I"},
        "effFrom": "2015-02-05T00:00:00", "effTo": None,
        "children": [{
            "id": "d1", "level": "Article", "title": "Điều 1. X", "ptype": 5,
            "orderIndex": 2, "isLeaf": True,
            "content": {"title": "Điều 1", "content": "Điều 1. X<br>noi dung"},
            "effFrom": "2015-02-05T00:00:00", "effTo": None, "children": [],
        }],
    }]
    rows = sp._flatten(tree, van_ban_id="VB")
    assert [r["id"] for r in rows] == ["c1", "d1"]  # cha truoc con
    assert rows[0]["parent_id"] is None and rows[0]["cap"] == "chuong"
    assert rows[1]["parent_id"] == "c1" and rows[1]["cap"] == "dieu"
    assert rows[1]["duong_dan"] == "CI>D1"
    assert rows[1]["hieu_luc_tu"] == date(2015, 2, 5)
    assert rows[0]["van_ban_id"] == "VB"


def test_flatten_bo_qua_level_chua_map():
    tree = [{"id": "x", "level": "Khac", "title": "?", "children": []}]
    assert sp._flatten(tree, "VB") == []
