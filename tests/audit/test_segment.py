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
    # Khoan NGAN (< 300 tu) co Diem -> GOP Diem vao Khoan thanh 1 don vi (giam so lan goi LLM)
    caps = {dv.cap for dv in kq.don_vi}
    assert caps == {"khoan"}
    assert len(kq.don_vi) == 2          # K1 D1 (da gop a,b) + K1 D2
    khoan_list = [dv for dv in kq.don_vi if dv.cap == "khoan"]
    assert all(k.tieu_de in {"Phạm vi", "Giải thích"} for k in khoan_list)
    # Khoan 1 Dieu 1 da gop ca Diem a va b vao noi_dung
    k1 = next(k for k in khoan_list if "Nội dung" in k.noi_dung)
    assert "Diem a" in k1.noi_dung and "Diem b" in k1.noi_dung


def test_khoan_dai_giu_diem_rieng():
    """Khoan + Diem qua dai (>= 300 tu) -> KHONG gop, giu Khoan va tung Diem rieng."""
    big = " ".join(["noi"] * 300)
    text = f"Điều 1. Phạm vi\n1. Mo dau khoan.\na) {big}\nb) diem ngan.\n"
    kq = segment_du_thao(text, "TL-big")
    caps = {dv.cap for dv in kq.don_vi}
    assert "diem" in caps              # qua dai -> tach Diem rieng
    assert sum(dv.cap == "diem" for dv in kq.don_vi) == 2


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


def test_du_thao_van_xuoi_khong_de_muc():
    """Du thao van xuoi thuan khong co de muc La Ma (I, II) hay Dieu van khong bi bo qua."""
    text = (
        "UBND tinh ban hanh quy dinh tiep cong dan.\n\n"
        "Can bo tiep cong dan khong duoc tu y tu choi tiep dan.\n"
        "Moi truong hop tu choi phai lap bien ban theo quy dinh.\n"
    )
    kq = segment_du_thao(text, "TL-prose")
    assert kq.co_cau_truc_dieu is False
    assert len(kq.don_vi) >= 1
    assert any("tiep cong dan" in dv.noi_dung for dv in kq.don_vi)


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


def test_bo_co_quan_ky_cuoi_vb():
    """Co quan ban hanh / chuc danh nguoi ky (CHU HOA) o cuoi VB khong dinh vao chunk;
    nhung noi dung chu thuong ('Chu tich ...') van giu."""
    text = (
        "Điều 19. Xử lý sau giải quyết\n"
        "Chủ tịch Ủy ban nhân dân xã có trách nhiệm áp dụng biện pháp xử lý.\n"
        "Đối với vụ việc tố cáo, đơn vị được giao cấp quyền xem hồ sơ điện tử cho người bị tố cáo.\n"
        "TÒA ÁN NHÂN DÂN TỐI CAO\n"
        "CHÁNH ÁN\n"
    )
    kq = segment_du_thao(text, "TL-ky")
    blob = " ".join(dv.noi_dung for dv in kq.don_vi)
    assert "TÒA ÁN NHÂN DÂN TỐI CAO" not in blob and "CHÁNH ÁN" not in blob
    assert "Chủ tịch Ủy ban nhân dân xã có trách nhiệm" in blob   # noi dung chu thuong: giu
    assert "người bị tố cáo" in blob


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


def test_phu_luc_kem_theo_va_block_ky():
    """QĐ kèm theo QUY ĐỊNH: tiêu đề phụ lục không dồn vào Điều QĐ trước; block ký
    (TỈNH.../Số:.../CỘNG HÒA 'HÒA'/Nơi nhận + danh sách) không dồn vào Điều cuối."""
    text = (
        "QUYẾT ĐỊNH\n"
        "Điều 3. Chánh Văn phòng chịu trách nhiệm thi hành Quyết định này.\n"
        "QUY ĐỊNH\n"
        "Về tiếp công dân, giải quyết khiếu nại\n"
        "(Kèm theo Quyết định số      /2026/QĐ-UBND ngày ... năm 2026 của UBND tỉnh)\n"
        "___________\n"
        "Chương I\n"
        "Điều 1. Phạm vi điều chỉnh\n"
        "Quy định này quy định về việc tiếp công dân.\n"
        "Điều 16. Điều khoản thi hành\n"
        "Trong quá trình thực hiện, nếu vướng mắc thì phản ánh về Thanh tra tỉnh./.\n"
        "ỦY BAN NHÂN DÂN\n"
        "TỈNH ...\n"
        "Số:      /2026/QĐ-UBND\n"
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Độc lập - Tự do - Hạnh phúc\n"
        "Nơi nhận:\n"
        "- Như Điều 3;\n"
        "- Lưu: VT, TTr.\n"
        "TM. ỦY BAN NHÂN DÂN\n"
        "CHỦ TỊCH\n"
    )
    kq = segment_du_thao(text, "TL-pl")
    blob = " ".join(dv.noi_dung for dv in kq.don_vi)
    # Khong dinh tieu de phu luc / block ky
    for rac in ("QUY ĐỊNH", "Kèm theo", "Nơi nhận", "/QĐ-UBND", "CỘNG", "Như Điều 3",
                "Lưu: VT", "CHỦ TỊCH", "TỈNH ..."):
        assert rac not in blob, f"segment dinh rac: {rac!r}"
    # Noi dung that cua phu luc van con (body Dieu 1 + tieu de dung)
    assert "tiếp công dân" in blob
    assert any(dv.tieu_de == "Phạm vi điều chỉnh" for dv in kq.don_vi)
    d16 = next(dv for dv in kq.don_vi if dv.so_dieu == "16")
    assert d16.noi_dung.endswith("./.")
