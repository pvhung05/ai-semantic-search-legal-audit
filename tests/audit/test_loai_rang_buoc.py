"""Test _loai_rang_buoc: nhan dien san/tran/trao_quyen tu keyword (truoc LLM)."""
from app.doisanh.retrieval.can_cu import _loai_rang_buoc


def test_thoi_han_la_tran():
    # Deadline = tran thoi gian: du thao dai hon -> vi pham. (ca that bai truoc day)
    assert "tran" in _loai_rang_buoc("Trong thời hạn 07 ngày làm việc kể từ ngày ra kết luận...")
    assert "tran" in _loai_rang_buoc("Chậm nhất là 05 ngày làm việc kể từ ngày ban hành...")


def test_san_tran_trao_quyen_co_ban():
    assert _loai_rang_buoc("Mức lương ít nhất 300%") == ["san"]
    assert _loai_rang_buoc("Làm thêm không quá 300 giờ/năm") == ["tran"]
    assert "trao_quyen" in _loai_rang_buoc("Thời gian do hai bên thỏa thuận")
    assert _loai_rang_buoc("Nội dung hành chính không có số") == ["khong_ro"]


def test_do_nguyen_nhan_khong_kich_hoat_trao_quyen():
    # 'do' mang nghia nguyen nhan (lien tu) khong duoc coi la trao quyen
    assert "trao_quyen" not in _loai_rang_buoc(
        "Việc xem xét khiếu nại, tố cáo để thụ lý cần kéo dài thời gian do cần xác minh thêm theo quy định của Luật khiếu nại, Luật tố cáo"
    )
    assert "trao_quyen" not in _loai_rang_buoc(
        "Kéo dài thời hạn do sự kiện bất khả kháng hoặc trở ngại khách quan"
    )
    assert "trao_quyen" not in _loai_rang_buoc(
        "Chậm thông báo do lỗi của người khiếu nại"
    )

    # Ca Dieu 28 Khoan 1 Luat Tiep cong dan 42/2013/QH13: phai la tran, KHONG phai trao_quyen
    dieu_28_k1 = (
        "Trong thời hạn 10 ngày làm việc, kể từ ngày tiếp nhận nội dung khiếu nại, tố cáo, kiến nghị, phản ánh, "
        "người tiếp công dân có trách nhiệm trả lời trực tiếp hoặc thông báo bằng văn bản đến người đã đến khiếu nại... "
        "b) Việc xem xét khiếu nại, tố cáo để thụ lý cần kéo dài thời gian do cần xác minh thêm..."
    )
    rb = _loai_rang_buoc(dieu_28_k1)
    assert "tran" in rb
    assert "trao_quyen" not in rb


def test_trao_quyen_cac_chu_the_hop_le():
    assert "trao_quyen" in _loai_rang_buoc("Mức chi do Bộ Tài chính quy định")
    assert "trao_quyen" in _loai_rang_buoc("Chế độ do Chính phủ quy định")
    assert "trao_quyen" in _loai_rang_buoc("Thời hạn do Thủ trưởng đơn vị quyết định")
    assert "trao_quyen" in _loai_rang_buoc("Tiêu chuẩn do người có thẩm quyền ban hành")
    assert "trao_quyen" in _loai_rang_buoc("Giao Bộ Công an hướng dẫn thi hành")
    assert "trao_quyen" in _loai_rang_buoc("Mức phí do Ủy ban nhân dân cấp tỉnh ban hành")
