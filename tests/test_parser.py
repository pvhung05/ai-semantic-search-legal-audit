"""Test parser voi text toi gian theo cau truc Luat VN.

Khong bia noi dung luat; text o day la vi du cau truc toi thieu de kiem regex.
"""
from app.ingestion.parser import parse_van_ban
from app.models.schemas import VanBanMeta


def _meta(ten: str = "Van ban kiem tra", sua_doi: bool = False) -> VanBanMeta:
    return VanBanMeta(
        id="X-2026-01", so_hieu="01/2026/TT", ten=ten,
        loai="thong_tu", cap=7, la_van_ban_sua_doi=sua_doi,
    )


def test_dieu_khoan_diem_co_ban():
    text = (
        "Điều 1. Phạm vi\n"
        "1. Thông tư này quy định về A.\n"
        "2. Áp dụng với B, bao gồm:\n"
        "a) Trường hợp một;\n"
        "b) Trường hợp hai.\n"
        "\n"
        "Điều 2. Giải thích từ ngữ\n"
        "1. Thuật ngữ.\n"
    )
    parsed = parse_van_ban(text, _meta())
    assert len(parsed.dieu) == 2
    d1 = parsed.dieu[0]
    assert d1.so_dieu == "1" and d1.so_dieu_num == 1
    assert d1.tieu_de == "Phạm vi"
    assert len(d1.khoan) == 4  # 2 khoan + 2 diem
    k2 = d1.khoan[1]
    assert k2.so_khoan == "2" and k2.diem is None
    diem_a = d1.khoan[2]
    assert diem_a.diem == "a" and diem_a.so_khoan == "2"


def test_dieu_54a_so_chu():
    text = "Điều 54a. Bổ sung\n1. Nội dung.\n"
    parsed = parse_van_ban(text, _meta())
    assert parsed.dieu[0].so_dieu == "54a"
    assert parsed.dieu[0].so_dieu_num == 54


def test_canh_bao_nhay_so_dieu():
    text = (
        "Điều 1. A\n1. x.\n"
        "Điều 3. B\n1. y.\n"
    )
    parsed = parse_van_ban(text, _meta())
    assert any("nhay" in w for w in parsed.canh_bao)
    assert len(parsed.dieu) == 2  # khong dung


def test_can_cu_duoc_trich():
    text = (
        "Căn cứ Luật Ban hành văn bản quy phạm pháp luật năm 2015;\n"
        "Căn cứ Nghị định số 123/2016/NĐ-CP;\n"
        "Theo đề nghị của Bộ trưởng;\n"
        "\n"
        "Điều 1. A\n1. X.\n"
    )
    parsed = parse_van_ban(text, _meta())
    assert len(parsed.can_cu_tho) == 2
    assert "Luật Ban hành" in parsed.can_cu_tho[0]


def test_nhan_dien_van_ban_sua_doi_qua_ten():
    text = "Điều 1. Nội dung.\n1. X.\n"
    parsed = parse_van_ban(text, _meta(ten="Nghị định sửa đổi, bổ sung một số điều của NĐ 145/2020"))
    assert parsed.meta.la_van_ban_sua_doi is True


def test_dieu_khong_khoan_giu_noi_dung():
    # Dieu chi co 1 doan van, khong chia Khoan -> phai giu nguyen than Dieu.
    text = (
        "Điều 26. Tiền lương thử việc\n"
        "Tiền lương của người lao động trong thời gian thử việc do hai bên thỏa thuận "
        "nhưng ít nhất phải bằng 85% mức lương của công việc đó.\n"
        "\n"
        "Điều 27. Kết thúc thử việc\n"
        "1. Khi kết thúc thời gian thử việc, phải thông báo kết quả.\n"
    )
    parsed = parse_van_ban(text, _meta())
    d26 = parsed.dieu[0]
    assert d26.so_dieu == "26" and len(d26.khoan) == 0
    assert "ít nhất phải bằng 85%" in d26.noi_dung


def test_dieu_co_doan_mo_dau_truoc_khoan():
    # Doan mo dau cua Dieu (truoc Khoan 1) khong duoc mat.
    text = (
        "Điều 25. Thời gian thử việc\n"
        "Thời gian thử việc do hai bên thỏa thuận và bảo đảm điều kiện sau đây:\n"
        "1. Không quá 180 ngày với người quản lý doanh nghiệp;\n"
        "2. Không quá 60 ngày với công việc cần trình độ cao đẳng trở lên;\n"
    )
    parsed = parse_van_ban(text, _meta())
    d25 = parsed.dieu[0]
    assert len(d25.khoan) == 2
    assert "bảo đảm điều kiện sau đây" in d25.noi_dung


def test_dong_1_trong_ngoac_kep_khong_thanh_khoan():
    text = (
        'Điều 1. Trích dẫn\n'
        'Thông tư quy định: "Khi áp dụng điều này,\n'
        '1. phải tuân thủ nguyên tắc nêu trên".\n'
    )
    parsed = parse_van_ban(text, _meta())
    assert len(parsed.dieu) == 1
    # Khong duoc chia thanh Khoan 1 vi dang trong ngoac kep chua dong
    assert len(parsed.dieu[0].khoan) == 0
