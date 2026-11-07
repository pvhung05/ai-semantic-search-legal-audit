from app.doisanh.audit.segment import segment_du_thao


def test_du_thao_co_dieu():
    text = (
        "Căn cứ Luật Ban hành văn bản;\n"
        "Thông tư này quy định...\n"
        "\n"
        "Điều 1. Phạm vi\n"
        "1. Nội dung.\n"
        "a) Diem a;\n"
        "b) Diem b.\n"
        "Điều 2. Giải thích\n"
        "1. Thuật ngữ.\n"
    )
    kq = segment_du_thao(text, "TL-abc")
    assert kq.co_cau_truc_dieu is True
    assert len(kq.can_cu_tho) == 1
    # Khoan + Diem deu la chunk, Dieu khong tao chunk
    caps = {dv.cap for dv in kq.don_vi}
    assert caps == {"khoan", "diem"}
    # 2 Khoan + 2 Diem = 4
    assert len(kq.don_vi) == 4
    # Khoan co tieu_de = tieu_de Dieu cha; Diem co tieu_de = noi_dung Khoan cha
    khoan_list = [dv for dv in kq.don_vi if dv.cap == "khoan"]
    assert all(k.tieu_de in {"Phạm vi", "Giải thích"} for k in khoan_list)
    diem_list = [dv for dv in kq.don_vi if dv.cap == "diem"]
    # Diem cua K1 D1 phai co tieu_de = noi_dung cua K1 D1 = "Nội dung."
    assert any("Nội dung" in (d.tieu_de or "") for d in diem_list)


def test_id_duy_nhat_khi_lap_so_khoan():
    # Du thao trich lai nguyen van -> cung "Dieu 1" + "Khoan 1" xuat hien 2 lan.
    # Moi don vi phai co id duy nhat (PK du_thao_node), khong duoc dup.
    text = (
        "Điều 1. Phạm vi\n"
        "1. Noi dung A.\n"
        "Điều 1. Phạm vi (trich lai)\n"
        "1. Noi dung B.\n"
    )
    kq = segment_du_thao(text, "TL-dup")
    ids = [dv.id for dv in kq.don_vi]
    assert len(ids) == len(set(ids)), f"id bi trung: {ids}"


def test_du_thao_khong_dieu():
    text = (
        "I. Quy định chung\n"
        "1. Phạm vi.\n"
        "2. Đối tượng.\n"
        "II. Thực hiện\n"
        "a) Buoc 1;\n"
        "b) Buoc 2.\n"
    )
    kq = segment_du_thao(text, "TL-xyz")
    assert kq.co_cau_truc_dieu is False
    # Khong tao chunk cho tieu de muc "I." "II." -> chi 4 doan (2 so + 2 chu)
    assert all(dv.cap == "doan" for dv in kq.don_vi)
    assert len(kq.don_vi) == 4
    # Tieu de muc duoc gan vao moi doan
    tieu_des = {dv.tieu_de for dv in kq.don_vi}
    assert tieu_des == {"Quy định chung", "Thực hiện"}


def test_chuong_muc_khong_lam_ban_noi_dung():
    """Header Chuong/Muc giua cac Dieu: khong dinh vao noi dung Khoan truoc,
    va chuong duoc gan dung cho tung don vi."""
    text = (
        "Chương I. QUY ĐỊNH CHUNG\n"
        "Điều 1. Phạm vi\n"
        "1. Noi dung khoan mot.\n"
        "Chương II. HÀNH VI BỊ CẤM\n"
        "Mục 1. Chung\n"
        "Điều 2. Cấm\n"
        "1. Noi dung khoan hai.\n"
    )
    kq = segment_du_thao(text, "TL-c")
    blob = " ".join(dv.noi_dung for dv in kq.don_vi)
    assert "Chương" not in blob and "Mục" not in blob  # header khong lot vao noi dung
    by_khoan = {(dv.so_dieu, dv.so_khoan): dv for dv in kq.don_vi}
    assert by_khoan[("1", "1")].chuong == "I"
    assert by_khoan[("2", "1")].chuong == "II"
    assert by_khoan[("1", "1")].noi_dung == "Noi dung khoan mot."


def test_bo_quoc_hieu_tieu_ngu():
    """Block ky cuoi VB (quoc hieu/tieu ngu/dia danh-ngay) khong tao chunk."""
    text = (
        "I. Quy định chung\n"
        "6. Chánh án chịu trách nhiệm tổ chức thực hiện.\n"
        "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Độc lập - Tự do - Hạnh phúc\n"
        "Hà Nội, ngày tháng 10 năm 2026\n"
    )
    blob = " ".join(dv.noi_dung for dv in segment_du_thao(text, "TL-x").don_vi)
    assert "Chánh án" in blob
    assert "CỘNG" not in blob and "Độc lập" not in blob and "Hà Nội" not in blob
