"""Test trich toan van: document <html> va RSC flight (T-chunk fragment)."""
import pytest

from app.crawl.doc_api import _trich_doc_info, _trich_toan_van, trich_diem_bi_tac_dong


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


def test_doc_info_format_moi_body_noi_lien_dong_1():
    # vbpl 11/2026: HTML ket thuc '</body>' (khong con '</html>1:'), '1:{...}' noi lien sau T-chunk.
    # documentFields co object con {"id":...} -> ban cu rfind('{"id":') cat trung no -> 'Extra data'.
    # "<body>x</body>" = 14 byte = 0xE
    text = ('0:["$@1",["X",null]]\n2:TE,<body>x</body>'
            '1:{"id":"835e","docNum":"15/2026/TT-NHNN","documentFields":[{"id":"f1","name":"TCTD"}]}')
    info = _trich_doc_info(text)
    assert info["id"] == "835e" and info["docNum"] == "15/2026/TT-NHNN"


def test_doc_info_format_cu_html():
    text = '0:["$@1",["X",null]]\n2:T15,<html><b>x</b></html>\n1:{"id":"176350","docNum":"38/2024/TT-BYT"}\n'
    assert _trich_doc_info(text)["docNum"] == "38/2024/TT-BYT"


def test_doc_info_khong_co_chunk_1_bao_loi():
    with pytest.raises(RuntimeError):
        _trich_doc_info('0:["$@1",[]]\n')


def test_trich_rong_khi_khong_co_html():
    assert _trich_toan_van('0:["$@1",[]]\n') == ''
