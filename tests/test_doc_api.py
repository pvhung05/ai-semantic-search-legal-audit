"""Test trich toan van: document <html> va RSC flight (T-chunk fragment)."""
from app.crawl.doc_api import _trich_toan_van, trich_diem_bi_tac_dong


def test_trich_diem_bi_tac_dong():
    # HTML trang GET (RSC-escaped): diem co `type` = bi tac dong; khong `type` = bo qua.
    html = (
        r'<p id=\"d51c1d80-316a-11f1-ad5f-e50472146e81\" class=\"prov-clause\">7.</p>'
        r'<p id=\"d51c4490-316a-11f1-9b0c-596617eecf12\" class=\"prov-clause\" '
        r'type=\"13:3b8d0990-eb7e-11f0-908f-490cc25d31a8\">8.</p>'
    )
    assert trich_diem_bi_tac_dong(html) == [
        ("d51c4490-316a-11f1-9b0c-596617eecf12", 13, "3b8d0990-eb7e-11f0-908f-490cc25d31a8"),
    ]


def test_trich_document_html():
    text = 'prefix\n<html><body>Noi dung</body></html>\nsuffix'
    assert _trich_toan_van(text) == '<html><body>Noi dung</body></html>'


def test_trich_rsc_flight_t_chunk():
    # chunk "2" la text-literal 'T<hexlen>,<bytes>'; "<div>abc</div>" = 14 byte = 0xE
    text = '0:["$@1",["X",null]]\n2:TE,<div>abc</div>\n'
    assert _trich_toan_van(text) == '<div>abc</div>'


def test_trich_rong_khi_khong_co_html():
    assert _trich_toan_van('0:["$@1",[]]\n') == ''
