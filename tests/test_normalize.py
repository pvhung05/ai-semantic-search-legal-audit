from app.doisanh.ingestion.normalize import chuan_hoa_dong, chuan_hoa_so_sanh, chuan_hoa_text


def test_bo_khoang_trang_kep():
    assert chuan_hoa_dong("hello   world\t  !") == "hello world !"


def test_thay_dau_cach_khong_ngan():
    assert chuan_hoa_dong("a b c") == "a b c"


def test_thay_ngoac_kep_thong_minh():
    assert chuan_hoa_dong("“hello”") == '"hello"'


def test_hyphen_wrap():
    assert "quy-\ndinh" not in chuan_hoa_text("quy-\ndinh")
    assert "quydinh" in chuan_hoa_text("quy-\ndinh")


def test_rut_gon_dong_trong():
    out = chuan_hoa_text("a\n\n\n\nb")
    assert out == "a\n\nb"


def test_chuan_hoa_so_sanh_bo_dau_kep():
    assert chuan_hoa_so_sanh("  Hello   WORLD  ") == "hello world"
