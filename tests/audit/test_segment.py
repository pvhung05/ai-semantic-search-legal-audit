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
