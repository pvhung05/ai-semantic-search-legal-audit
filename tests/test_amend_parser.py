from app.doisanh.ingestion.amend_parser import parse_lenh_sua_doi
from app.core.models.schemas import Dieu, Khoan, VanBanMeta, VanBanParsed


def _vb(dieu_list: list[Dieu], ten: str = "NĐ sửa đổi 145/2020/NĐ-CP") -> VanBanParsed:
    meta = VanBanMeta(
        id="ND-SD-01", so_hieu="99/2026/NĐ-CP", ten=ten,
        loai="nghi_dinh", cap=5, la_van_ban_sua_doi=True,
    )
    return VanBanParsed(meta=meta, dieu=dieu_list)


def test_lenh_sua_doi_khoan():
    d = Dieu(so_dieu="1", so_dieu_num=1,
             tieu_de="Sửa đổi, bổ sung một số điều của Nghị định số 145/2020/NĐ-CP",
             noi_dung="", thu_tu=1,
             khoan=[Khoan(so_khoan="1",
                          noi_dung="Sửa đổi Khoản 2 Điều 54 như sau: ...",
                          thu_tu=1)])
    lenh = parse_lenh_sua_doi(_vb([d]))
    assert len(lenh) == 1
    assert lenh[0].loai == "sua_doi"
    assert lenh[0].dich_so_dieu == "54"
    assert lenh[0].dich_so_khoan == "2"
    assert lenh[0].dich_so_hieu == "145/2020/NĐ-CP"


def test_lenh_bai_bo():
    d = Dieu(so_dieu="2", so_dieu_num=2,
             tieu_de="Sửa đổi, bổ sung một số điều của Nghị định số 145/2020/NĐ-CP",
             noi_dung="", thu_tu=2,
             khoan=[Khoan(so_khoan="1",
                          noi_dung="Bãi bỏ Khoản 3 Điều 12.",
                          thu_tu=1)])
    lenh = parse_lenh_sua_doi(_vb([d]))
    assert lenh[0].loai == "bai_bo"
    assert lenh[0].dich_so_dieu == "12"
    assert lenh[0].dich_so_khoan == "3"


def test_lenh_thay_cum_tu():
    d = Dieu(so_dieu="3", so_dieu_num=3,
             tieu_de="Sửa đổi, bổ sung một số điều của Nghị định số 145/2020/NĐ-CP",
             noi_dung="", thu_tu=3,
             khoan=[Khoan(so_khoan="1",
                          noi_dung='Thay cụm từ "30 ngày" bằng "45 ngày".',
                          thu_tu=1)])
    lenh = parse_lenh_sua_doi(_vb([d]))
    assert lenh[0].loai == "thay_cum_tu"
    assert lenh[0].cum_tu_cu == "30 ngày"
    assert lenh[0].cum_tu_moi == "45 ngày"


def test_lenh_khong_khop_ghi_tho():
    d = Dieu(so_dieu="4", so_dieu_num=4,
             tieu_de="Sửa đổi, bổ sung một số điều của Nghị định số 145/2020/NĐ-CP",
             noi_dung="", thu_tu=4,
             khoan=[Khoan(so_khoan="1",
                          noi_dung="Khoản này mô tả không rõ ràng, không khớp pattern.",
                          thu_tu=1)])
    lenh = parse_lenh_sua_doi(_vb([d]))
    assert len(lenh) == 1
    assert lenh[0].tin_cay == "can_ra_soat"
