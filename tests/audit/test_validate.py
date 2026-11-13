"""cat_theo_pham_vi: de_xuat_sua phai thay DUNG phan sai (snippet), khong lap lai ca doan."""
from app.doisanh.audit.validate import cat_theo_pham_vi, tach_can_cu_goc

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


def test_tach_can_cu_goc_co_khoi_llm():
    raw = (
        "[CĂN CỨ NÀY Văn bản bị sửa đổi, bổ sung Khoản 5, Điều 2 - Luật số 136/2025/QH15 — DÙNG NỘI DUNG SAU KHI SỬA LÀM CHUẨN]\n"
        "Nội dung sau khi sửa: 5. Sửa đổi điểm h...\n"
        "Điều 12. Quyền của người khiếu nại\n"
        "1. Quyền một"
    )
    res = tach_can_cu_goc(raw)
    assert "[CĂN CỨ NÀY" not in res
    assert "Nội dung sau khi sửa" not in res
    assert res == "Điều 12. Quyền của người khiếu nại\n1. Quyền một"


def test_tach_can_cu_goc_khong_co_khoi_llm():
    raw = "Điều 107. Làm thêm giờ không quá 300 giờ."
    assert tach_can_cu_goc(raw) == raw
