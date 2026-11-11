"""cat_theo_pham_vi: de_xuat_sua phai thay DUNG phan sai (snippet), khong lap lai ca doan."""
from app.doisanh.audit.validate import cat_theo_pham_vi

DOAN = "Câu một đúng. Câu hai sai thời hạn 30 ngày. Câu ba đúng."
SNIP = "Câu hai sai thời hạn 30 ngày."


def test_cat_khi_llm_chep_lai_ca_doan():
    de_xuat = "Câu một đúng. Câu hai sai thời hạn 10 ngày. Câu ba đúng."
    assert cat_theo_pham_vi(de_xuat, SNIP, DOAN) == "Câu hai sai thời hạn 10 ngày."


def test_giu_nguyen_khi_dung_pham_vi():
    assert cat_theo_pham_vi("Câu hai thời hạn 10 ngày.", SNIP, DOAN) == "Câu hai thời hạn 10 ngày."


def test_chi_bo_doan_sai_thi_rong():
    # LLM muon xoa phan sai: chep lai doan khong co snippet -> sau khi cat con rong
    assert cat_theo_pham_vi("Câu một đúng. Câu ba đúng.", SNIP, DOAN) == ""


def test_snippet_khong_nam_trong_doan_thi_khong_dung():
    assert cat_theo_pham_vi("X", "không có", DOAN) == "X"
