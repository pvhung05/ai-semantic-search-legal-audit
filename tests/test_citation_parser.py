from app.doisanh.ingestion.citation_parser import trich_dan_chieu


def test_dan_chieu_noi_bo():
    text = "Theo khoản 2 Điều 54 Luật này, cơ quan phải..."
    dc = trich_dan_chieu(text)
    assert len(dc) == 1
    assert dc[0].la_noi_bo
    assert dc[0].so_dieu == "54" and dc[0].so_khoan == "2"


def test_dan_chieu_ngoai_co_so_hieu():
    text = "khoản 1 Điều 5 của Nghị định số 145/2020/NĐ-CP"
    dc = trich_dan_chieu(text)
    assert len(dc) == 1
    assert dc[0].so_hieu == "145/2020/NĐ-CP"
    assert dc[0].so_dieu == "5"


def test_dan_chieu_co_diem():
    text = "điểm a khoản 3 Điều 12 Luật này"
    dc = trich_dan_chieu(text)
    assert len(dc) == 1
    assert dc[0].diem == "a"
    assert dc[0].so_khoan == "3"
    assert dc[0].so_dieu == "12"


def test_nhieu_dan_chieu():
    text = "Thực hiện theo khoản 1 Điều 2 và Điều 5 Luật này"
    dc = trich_dan_chieu(text)
    assert len(dc) == 2
