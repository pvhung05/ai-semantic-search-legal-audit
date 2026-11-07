"""Test danh dau VI_PHAM len docx: to do + comment AI LEGAL."""
from docx import Document

from app.doisanh.audit.docx_track import danh_dau_vi_pham, _tim_paragraph


def test_tim_paragraph_chua_nhau():
    paras = ["Điều 1. Phạm vi", "2. Người lao động được nghỉ 10 ngày.", "Điều 2."]
    assert _tim_paragraph(paras, "2. Người lao động được nghỉ 10 ngày.") == [1]


def test_danh_dau_to_do_va_comment(tmp_path):
    src = tmp_path / "du_thao.docx"
    out = tmp_path / "du_thao_marked.docx"
    d = Document()
    d.add_paragraph("Điều 1. Thời giờ làm việc")
    d.add_paragraph("2. Người lao động làm thêm không quá 400 giờ mỗi năm.")
    d.save(str(src))

    ket_qua = {"ket_qua": {"VI_PHAM": [{
        "noi_dung_du_thao": "2. Người lao động làm thêm không quá 400 giờ mỗi năm.",
        "can_cu_phap_ly": {"trich_dan": "Điều 107 BLLĐ: không quá 300 giờ/năm."},
        "de_xuat_sua": "Sửa 400 thành 300 giờ.",
    }]}}
    n = danh_dau_vi_pham(src, ket_qua, out)
    assert n == 1

    d2 = Document(str(out))
    # doan vi pham co track change THAT (w:ins/w:del) de Word bat/tat + Accept/Reject
    p = d2.paragraphs[1]
    assert "w:del" in p._p.xml and "w:ins" in p._p.xml
    # co comment AI LEGAL chua ca trich_dan + de_xuat
    cmts = list(d2.comments)
    assert len(cmts) == 1
    assert cmts[0].author == "AI LEGAL"
    assert "Điều 107 BLLĐ" in cmts[0].text and "300 giờ" in cmts[0].text


def test_khong_vi_pham_khong_danh_dau(tmp_path):
    src = tmp_path / "x.docx"; out = tmp_path / "x_out.docx"
    Document().save(str(src))
    assert danh_dau_vi_pham(src, {"ket_qua": {"VI_PHAM": []}}, out) == 0


def test_thay_snippet_giu_phan_con_lai(tmp_path):
    """VI_PHAM co snippet: thay dung phan sai bang de_xuat_sua, giu phan con lai, to do phan moi."""
    src = tmp_path / "d.docx"
    out = tmp_path / "o.docx"
    d = Document()
    d.add_paragraph("Người lao động làm thêm không quá 400 giờ mỗi năm theo quy định.")
    d.save(str(src))
    ket = {"ket_qua": {"VI_PHAM": [{
        "noi_dung_du_thao": "400 giờ",
        "can_cu_phap_ly": {"trich_dan": "Điều 107: 300 giờ/năm."},
        "de_xuat_sua": "300 giờ",
    }]}}
    assert danh_dau_vi_pham(src, ket, out) == 1
    p = Document(str(out)).paragraphs[0]
    xml = p._p.xml
    # track change THAT: '400' boc <w:del> (delText), '300' boc <w:ins>
    assert "<w:del " in xml and "<w:delText" in xml and "400" in xml
    assert "<w:ins " in xml and "300" in xml
    # phan giong nhau giu nguyen (run thuong, van nam trong .text)
    assert "Người lao động" in p.text and "theo quy định" in p.text
    assert "giờ" in p.text
    # '400' da xoa -> khong con trong .text (nam trong w:delText)
    assert "400" not in p.text
