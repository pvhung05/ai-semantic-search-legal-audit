"""Test danh dau VI_PHAM len docx: to do + comment AI LEGAL."""
from docx import Document

from app.doisanh.audit.docx_track import danh_dau_vi_pham, _tim_paragraph, _noi_dung_comment, _tach_can_cu_goc


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


def test_noi_dung_comment_co_tac_dong_sua_doi():
    """Comment tach ro 2 khoi: can cu goc va can cu tac dong, ngan cach bang 1 dong trong."""
    trich_dan_hon_hop = (
        "[CĂN CỨ NÀY Văn bản bị sửa đổi, bổ sung Khoản 5, Điều 2 - Luật số 136/2025/QH15 "
        "(hiệu lực 2026-07-01) — DÙNG NỘI DUNG SAU KHI SỬA LÀM CHUẨN]\n"
        "Nội dung sau khi sửa: 5. Sửa đổi, bổ sung điểm h khoản 1 Điều 12 như sau:\n"
        "“h) Nhận văn bản trả lời về việc thụ lý...”.\n"
        "Điều 12. Quyền, nghĩa vụ của người khiếu nại\n"
        "1. Người khiếu nại có các quyền sau đây:\n"
        "a) Tự mình khiếu nại."
    )
    vp = {
        "noi_dung_du_thao": "Không được khiếu nại",
        "can_cu_phap_ly": {
            "so_hieu": "02/2011/QH13",
            "ten_van_ban": "Luật Khiếu nại",
            "vi_tri": "Điều 12",
            "trich_dan": trich_dan_hon_hop,
            "da_sua": True,
            "sua_boi": "Khoản 5, Điều 2 - Luật số 136/2025/QH15",
            "ngay_hieu_luc": "2026-07-01",
            "da_het_hieu_luc": False,
            "noi_dung_sau_sua": (
                "5. Sửa đổi, bổ sung điểm h khoản 1 Điều 12 như sau:\n"
                "“h) Nhận văn bản trả lời về việc thụ lý...”."
            ),
        },
    }
    comment = _noi_dung_comment(vp)

    # 1. Khong chua header ky thuat
    assert "[CĂN CỨ NÀY" not in comment

    # 2. Tach ro 2 phan boi 1 dong trong (\n\n)
    khoi = comment.split("\n\n")
    assert len(khoi) == 2

    # Khoi 1: can cu goc (co dinh danh va text goc, khong dinh noi dung sua)
    assert "Căn cứ pháp lý: 02/2011/QH13 – Điều 12 (Luật Khiếu nại)" in khoi[0]
    assert "Điều 12. Quyền, nghĩa vụ của người khiếu nại" in khoi[0]
    assert "a) Tự mình khiếu nại." in khoi[0]
    assert "Nội dung sau khi sửa" not in khoi[0]

    # Khoi 2: can cu tac dong
    assert "⚠ Điều 12 đã được sửa đổi bởi Khoản 5, Điều 2 - Luật số 136/2025/QH15 (hiệu lực 2026-07-01):" in khoi[1]
    assert "“h) Nhận văn bản trả lời về việc thụ lý...”." in khoi[1]


def test_noi_dung_comment_bai_bo():
    vp = {
        "can_cu_phap_ly": {
            "so_hieu": "02/2011/QH13",
            "vi_tri": "Điều 15",
            "trich_dan": "Điều 15. Quy định cũ...",
            "da_sua": True,
            "sua_boi": "Luật số 99/2025/QH15",
            "ngay_hieu_luc": "2026-01-01",
            "da_het_hieu_luc": True,
        },
    }
    comment = _noi_dung_comment(vp)
    assert "⚠ Điều 15 đã bị bãi bỏ bởi Luật số 99/2025/QH15 (hiệu lực 2026-01-01) — không còn hiệu lực." in comment


def test_noi_dung_comment_khong_tac_dong():
    vp = {
        "can_cu_phap_ly": {
            "so_hieu": "45/2019/QH14",
            "ten_van_ban": "Bộ luật Lao động",
            "vi_tri": "Điều 107",
            "trich_dan": "Điều 107. Làm thêm giờ không quá 300 giờ.",
            "da_sua": False,
        },
    }
    comment = _noi_dung_comment(vp)
    assert "⚠" not in comment
    assert "Căn cứ pháp lý: 45/2019/QH14 – Điều 107 (Bộ luật Lao động)" in comment
    assert "Điều 107. Làm thêm giờ không quá 300 giờ." in comment
