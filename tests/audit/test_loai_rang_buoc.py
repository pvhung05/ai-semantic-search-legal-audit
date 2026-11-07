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
