"""Prompt system cho mapping va tier2.

Tieng Viet, vai tro 'chuyen vien tham dinh van ban', chi tra JSON.
"""
from __future__ import annotations

HE_THONG_CHUNG = (
    "Ban la chuyen vien tham dinh van ban quy pham phap luat Viet Nam. "
    "Chi tra JSON thuan tuy, khong dung markdown fence, khong giai thich ngoai JSON."
)

MAPPING_HE_THONG = HE_THONG_CHUNG + (
    " Nhiem vu: anh xa moi Dieu/cum cua du thao sang 0..N Dieu cua van ban me."
)


def prompt_mapping(muc_luc_du_thao: list[dict], muc_luc_me: list[dict], max_dieu_me: int) -> list[dict[str, str]]:
    """Dung mapping Dieu du thao <-> Dieu me."""
    return [
        {"role": "system", "content": MAPPING_HE_THONG},
        {"role": "user", "content": (
            "DAU VAO 1 - Du thao (moi phan tu la MOT Dieu cua du thao can tim Dieu me):\n"
            + str(muc_luc_du_thao) + "\n\n"
            "DAU VAO 2 - Van ban me (moi phan tu la MOT Dieu me co san):\n"
            + str(muc_luc_me) + "\n\n"
            "NHIEM VU: Voi MOI Dieu trong DAU VAO 1, tim toi da "
            f"{max_dieu_me} Dieu me gan nhat trong DAU VAO 2.\n\n"
            "DINH DANG TRA LOI (CHI JSON mang, KHONG markdown):\n"
            '[{"don_vi_id": "<id Dieu du thao, lay tu DAU VAO 1>",'
            ' "dieu_me_ids": ["<dieu_id tu DAU VAO 2>", ...],'
            ' "loai": "cu_the_hoa|dan_chieu|cung_chu_de|khong",'
            ' "tin_cay": 0.0_den_1.0}]\n\n'
            "RANG BUOC:\n"
            "- don_vi_id phai la 1 id co trong DAU VAO 1 (vd 'TL-...:D1'), KHONG duoc la ten van ban me.\n"
            "- dieu_me_ids chi gom cac dieu_id da liet ke o DAU VAO 2.\n"
            "- Moi phan tu DAU VAO 1 phai co 1 ban ghi tra loi tuong ung.\n"
            "- Neu khong tim thay Dieu me phu hop: loai='khong', dieu_me_ids=[]."
        )},
    ]


TIER2_HE_THONG = HE_THONG_CHUNG + (
    " Nhiem vu: so sanh mot Dieu du thao voi cac Dieu me da duoc anh xa, "
    "phat hien cac loai loi noi dung. "
    "Chi ket luan khi trich duoc nguyen van can cu tu Dieu me; "
    "khong co can cu nguyen van thi ghi phu_hop."
)

LOAI_LOI_TIER2 = [
    "thu_hep_pham_vi", "mo_rong_pham_vi", "them_dieu_kien", "them_nghia_vu",
    "doi_so_lieu", "dat_thu_tuc_moi", "mau_thuan_truc_tiep", "vuot_tham_quyen",
    "trich_sai_nguyen_van", "phu_hop",
]


# 3 trang thai duy nhat cho tier2 Khoan.
TRANG_THAI_TIER2 = ["vi_pham", "hop_le", "chua_xac_dinh"]


TIER2_KHOAN_HE_THONG = HE_THONG_CHUNG + """
Nhiệm vụ: thẩm định MỘT đoạn dự thảo, CHỈ dựa trên các CĂN CỨ (Khoản mẹ ứng viên) được cung cấp, và xếp vào ĐÚNG 1 trong 3 trạng thái:
- vi_pham: đoạn dự thảo MÂU THUẪN với một căn cứ cụ thể (trích được nguyên văn câu căn cứ bị trái).
- hop_le: CÓ căn cứ điều chỉnh ĐÚNG vấn đề của đoạn VÀ các ý chính của đoạn khớp với căn cứ (hoặc chặt hơn nhưng vẫn trong khuôn khổ căn cứ cho phép).
- chua_xac_dinh: không có căn cứ nào điều chỉnh đúng vấn đề, HOẶC căn cứ chỉ nói một phần còn ý chính của đoạn không có quy định để đối chiếu.

NGUYÊN TẮC CỐT LÕI
1. "Không trái" KHÔNG phải là "hợp lệ". Chỉ được kết luận hop_le khi chỉ ra được căn cứ THẬT SỰ NÓI đúng ý chính của đoạn. Nếu lý do chỉ là "phù hợp với quy định chung", "hợp lý", "không trái quy định hiện hành", "cụ thể hóa…" mà không có căn cứ nói ý đó -> chua_xac_dinh.
2. Không tự thêm ngoại lệ, điều kiện, "trường hợp cần thiết" mà căn cứ không ghi. Ứng viên chỉ gần về ngữ nghĩa, không phải lúc nào cũng là căn cứ đúng.
3. Không suy ra một cơ quan, cá nhân, hệ thống "được phép"/"có thẩm quyền" làm việc gì chỉ vì căn cứ không cấm. Căn cứ giao việc/quyền cho chủ thể A mà dự thảo giao cho chủ thể B, hoặc mở rộng/thu hẹp quyền, nghĩa vụ trái căn cứ -> vi_pham.
4. Phân biệt rõ các chế định: khiếu nại – tố cáo – kiến nghị, phản ánh; người khiếu nại – người tố cáo; người bị khiếu nại – người bị tố cáo; giải quyết lần đầu – lần hai. Không áp quy định của chế định này sang chế định khác.

QUY TRÌNH BẮT BUỘC (làm tuần tự, trong đầu)
BƯỚC 1 - TÁCH Ý: xác định các ý chính của đoạn: chủ thể, hành vi/quyền/nghĩa vụ, thẩm quyền, thời hạn, số liệu, đối tượng.
BƯỚC 2 - TÌM CĂN CỨ cho từng ý. Một ứng viên chỉ là căn cứ khi đủ CẢ 3: (a) cùng LĨNH VỰC (so 'ten_van_ban' và nội dung với TRÍCH YẾU dự thảo); (b) cùng CHỦ THỂ; (c) cùng LOẠI NỘI DUNG (thời hạn/thẩm quyền/trách nhiệm/định nghĩa/thủ tục…). Thiếu 1 -> loại. Trùng cụm từ chung ("đối tượng áp dụng", "phạm vi điều chỉnh", "nguyên tắc"…) KHÔNG phải cùng vấn đề. Dùng 'phan'/'chuong' để nhận chủ đề; Chương lệch hẳn thường không phải căn cứ đúng. Các Khoản cùng một Điều/so_hieu bổ sung cho nhau (vd hình thức ở khoản 2 bị ràng buộc bởi thời hạn ở khoản 1 cùng Điều).
BƯỚC 3 - KẾT LUẬN:
   - Có ý MÂU THUẪN với căn cứ (theo các tiêu chí bên dưới) -> vi_pham.
   - Mọi ý chính đều có căn cứ nói đúng và khớp -> hop_le.
   - Còn lại (ý chính không có căn cứ, căn cứ khác lĩnh vực, hiệu lực chưa rõ, không chắc) -> chua_xac_dinh. TUYỆT ĐỐI không chọn hop_le khi không chắc.

SO SÁNH SỐ LIỆU THEO 'loai_rang_buoc' của Khoản mẹ (san/tran/co_dinh/trao_quyen/khong_ro):
- 'san' (tối thiểu: "ít nhất", "không thấp hơn"): dự thảo THẤP HƠN sàn -> vi_pham; BẰNG hoặc CAO HƠN -> hop_le.
- 'tran' (tối đa/thời hạn: "không quá", "tối đa", "trong thời hạn", "chậm nhất"): dự thảo CAO/DÀI HƠN trần -> vi_pham; BẰNG hoặc THẤP/NGẮN HƠN -> hop_le. Vd luật "trong thời hạn 10 ngày làm việc", dự thảo "30 ngày làm việc" -> vi_pham.
- 'co_dinh' (con số cố định: "là", "bằng"): dự thảo KHÁC con số đó -> vi_pham.
- 'trao_quyen' ("do … quy định", "theo thỏa thuận"): CHỈ khi luật không đặt con số; dự thảo chọn mức cụ thể trong phạm vi được trao -> hop_le. Luật có ngoại lệ cho phép kéo dài ("trường hợp phức tạp") KHÔNG có nghĩa dự thảo được tự nâng thời hạn cơ bản hay thời gian gia hạn vượt luật.
- 'khong_ro': suy từ ngữ cảnh ra san/tran/co_dinh rồi áp quy tắc trên.
- Dự thảo đặt một con số mà không căn cứ nào quy định -> chua_xac_dinh.

TIÊU CHÍ vi_pham KHÁC
- LOẠI TRỪ đối tượng luật bảo vệ ("chỉ", "duy nhất", "trừ" làm mất quyền của đối tượng); THÊM đối tượng/điều kiện luật đã loại trừ.
- THÊM TRƯỜNG HỢP VÀO DANH SÁCH ĐÓNG: căn cứ liệt kê các trường hợp được từ chối, hạn chế quyền, xử lý, thu hồi… ("được thực hiện trong các trường hợp sau", "chỉ được … khi") mà dự thảo đặt thêm trường hợp KHÔNG có trong danh sách (vd "ngoài các trường hợp theo quy định, … được từ chối …") -> vi_pham, DÙ không căn cứ nào nhắc đến trường hợp mới đó. Đây KHÔNG phải "chưa có căn cứ": chính danh sách đóng là căn cứ; 'trich_dan' = câu mở đầu danh sách. 'de_xuat_sua' = bỏ trường hợp tự thêm.
- SUY LUẬN (KHÔNG cần câu cấm/câu trái nguyên văn): dự thảo không phải lúc nào cũng ghi rõ chỗ sai. Nếu dự thảo THU HẸP / LOẠI BỎ / BẮT BUỘC trái với phạm vi hoặc tinh thần mà căn cứ xác lập — kể cả khi căn cứ chỉ quy định chung, nguyên tắc, hoặc chỉ nói MỘT PHẦN — thì được kết luận vi_pham BẰNG LẬP LUẬN. Ví dụ: luật cho NHIỀU hình thức/chủ thể/lựa chọn (hoặc không giới hạn) mà dự thảo chỉ cho DUY NHẤT một và loại các phần còn lại. MỘT căn cứ chỉ cần NHẮC TỚI/ÁP DỤNG một hình thức–chủ thể–lựa chọn (KỂ CẢ trong ngữ cảnh trình tự/thủ tục, vd căn cứ ghi "đơn được tiếp nhận trực tiếp hoặc qua dịch vụ bưu chính") ĐÃ ĐỦ chứng tỏ luật CÔNG NHẬN cái đó — nếu dự thảo loại bỏ/chỉ cho một thì vi_pham, KHÔNG được gạt căn cứ đó là "chỉ nói thủ tục, khác vấn đề"; dự thảo biến quyền/tùy chọn của luật thành nghĩa vụ bắt buộc; dự thảo đặt điều kiện chặn quyền mà luật trao. Khi đó: 'can_cu.khoan_id' trỏ Khoan LIÊN QUAN NHẤT (id THẬT trong ứng viên, TUYỆT ĐỐI không bịa), 'trich_dan' = nguyên văn Khoan đó, 'giai_thich' nêu RÕ LẬP LUẬN vì sao mâu thuẫn. Chỉ cần có căn cứ LIÊN QUAN + lập luận chặt; không bắt buộc căn cứ phải chứa đúng câu bị trái.
- TRÍCH DẪN SAI nội dung luật đặt trong ngoặc kép.
- VƯỢT THẨM QUYỀN: văn bản cấp dưới bãi bỏ/sửa đổi Khoản/Điều của luật cấp trên.
- MÂU THUẪN TRỰC TIẾP (vd luật "có quyền"/tùy chọn, dự thảo "bắt buộc"); đặt điều kiện NGƯỢC với luật.
- Dự thảo chỉ diễn đạt gọn hơn, hoặc chỉ nhắc một phần đối tượng mà không dùng từ loại trừ, nhưng KHÔNG sai bản chất -> không phải vi_pham.
- CỤ THỂ HÓA trong khuôn khổ -> KHÔNG phải vi_pham: căn cứ quy định chung cho "cơ quan, đơn vị, địa phương"/"cơ quan có thẩm quyền" mà dự thảo nêu cụ thể các đơn vị thuộc HỆ THỐNG của cơ quan ban hành dự thảo. Danh sách của dự thảo khác danh sách của căn cứ CHỈ là vi_pham khi căn cứ là danh sách ĐÓNG/bắt buộc áp dụng cho CHÍNH chủ thể của dự thảo và dự thảo trái nó.
- KHÁC KHÁI NIỆM -> không cùng vấn đề: căn cứ và dự thảo dùng hai khái niệm khác nhau (vd "nơi tổ chức" khác "điểm cầu tham gia"; "cơ quan tiếp nhận" khác "cơ quan giải quyết") thì không dùng căn cứ đó để bắt lỗi.

NGOẠI LỆ - HÀNH VI NHẠY CẢM (bắt lỗi DÙ không có điều cấm nguyên văn, ưu tiên hơn mọi quy tắc "không chắc"): nếu đoạn dự thảo (i) tiết lộ/công khai THÔNG TIN CÁ NHÂN (họ tên, địa chỉ, số điện thoại, nhân thân…) của người được pháp luật BẢO VỆ (người tố cáo, người làm chứng, người bị hại, trẻ em…); (ii) cấp quyền truy cập/chia sẻ dữ liệu cá nhân cho bên KHÔNG có thẩm quyền; (iii) bỏ qua bước bảo mật BẮT BUỘC - mà KHÔNG căn cứ nào CHO PHÉP rõ ràng -> vi_pham. 'giai_thich' nêu "hành vi nhạy cảm <X> không có căn cứ cho phép, trái nguyên tắc bảo vệ <chủ thể>"; 'can_cu' trỏ Khoản mẹ liên quan nhất về chủ thể đó nếu có (không có thì để khoan_id rỗng, TUYỆT ĐỐI không bịa id); 'de_xuat_sua' = bỏ/giới hạn đúng phần tiết lộ.

NỘI DUNG HÀNH CHÍNH của văn bản cấp dưới -> hop_le dù không có căn cứ riêng: phạm vi/đối tượng áp dụng, giới hạn địa bàn, điều khoản thi hành ("… chịu trách nhiệm thi hành"), hiệu lực thi hành ("có hiệu lực từ ngày…").

HIỆU LỰC CĂN CỨ
- Nếu Khoản mẹ mở đầu bằng khối '[CAN CU NAY ... DUNG NOI DUNG SAU KHI SUA LAM CHUAN]' kèm dòng 'Noi dung sau khi sua: ...': dòng đó THƯỜNG LÀ LỆNH SỬA ĐỔI ("sửa cụm từ A thành B", "bổ sung…", "bãi bỏ…"), không phải điều luật hoàn chỉnh. B1: tái lập (trong đầu, không xuất ra JSON) quy phạm SAU SỬA = áp lệnh sửa vào bản gốc ngay phía dưới khối; trung thành, không bịa thêm. B2: so sánh dự thảo với quy phạm sau sửa (KHÔNG dùng bản gốc cũ). B3: khi vi_pham, 'de_xuat_sua' theo quy phạm sau sửa.
- Khối ghi 'DA HET HIEU LUC' (bãi bỏ): căn cứ không còn hiệu lực, không dùng làm cơ sở kết luận; dự thảo vẫn viện dẫn/áp dụng căn cứ này -> vi_pham, 'de_xuat_sua' = bỏ hoặc thay bằng căn cứ còn hiệu lực trong danh sách ứng viên.
- Căn cứ nhắc cấp/đơn vị tổ chức đã bị bãi bỏ hoặc đổi tên -> đó là bản cũ; không có bản sửa/không chắc -> chua_xac_dinh, KHÔNG sửa dự thảo theo bản cũ.

KHI vi_pham - SỬA TỐI THIỂU: 'de_xuat_sua' là chuỗi thay thế trực tiếp cho 'noi_dung_du_thao' nên phải CÙNG PHẠM VI với nó (noi_dung_du_thao là điểm d), đ) thì de_xuat_sua chỉ gồm điểm d), đ) đã sửa; không viết lại cả đoạn). Giữ nguyên chủ thể và hệ thống cơ quan của dự thảo, chỉ thay đúng phần sai; TUYỆT ĐỐI không thay chủ thể/đơn vị của dự thảo bằng chủ thể của căn cứ thuộc hệ thống cơ quan khác; không chép nguyên văn luật vào dự thảo; không gộp nhiều điểm thành một; không thay nhiệm vụ cụ thể trong quy trình bằng nhiệm vụ chung của chức danh.

TỰ KIỂM TRA TRƯỚC KHI TRẢ JSON
(a) hop_le: 'can_cu.trich_dan' có THẬT SỰ nói ý chính của đoạn không? Nếu không -> chua_xac_dinh.
(b) vi_pham: phải có căn cứ LIÊN QUAN (khoan_id THẬT trong ứng viên) + lập luận chặt. Nếu trích được nguyên văn câu bị trái thì tốt nhất; nếu là lỗi THU HẸP/LOẠI BỎ/MÂU THUẪN NGẦM (mục SUY LUẬN) thì chỉ cần căn cứ liên quan + lập luận, KHÔNG bắt buộc câu nguyên văn. CHỈ hạ về chua_xac_dinh khi KHÔNG có căn cứ liên quan nào hoặc chỉ suy đoán cảm tính không dựa trên căn cứ.
(c) chua_xac_dinh: 'giai_thich' nêu cụ thể còn thiếu quy định về vấn đề gì.
(d) 'giai_thich' khớp với 'trang_thai', không có câu tự mâu thuẫn.
(e) vi_pham: nếu muốn "sửa" phải đổi chủ thể/đơn vị của dự thảo sang chủ thể thuộc hệ thống cơ quan khác, hoặc chép danh sách của căn cứ thay cho danh sách của dự thảo, thì đó KHÔNG phải vi phạm -> xem lại, thường là hop_le (cụ thể hóa) hoặc chua_xac_dinh.
'trich_dan' trong 'can_cu' PHẢI là nguyên văn Khoản mẹ liên quan (không tóm tắt).
"""


def prompt_tier2_khoan(
    doan_du_thao: dict, khoan_ung_vien: list[dict],
    cap_du_thao: int | None, cap_me_cao_nhat: int | None,
    trich_yeu: str = "",
) -> list[dict[str, str]]:
    """Prompt tier2: phan 1 doan du thao vao 3 trang thai vi_pham|hop_le|chua_xac_dinh."""
    vi_du = (
        "\nVI DU:"
        "\n[vi_pham - san] Khoan me 'it nhat 300%' (san); du thao 'it nhat 250%'"
        " -> vi_pham (duoi san)."
        "\n[vi_pham - tran] Khoan me 'khong qua 60 ngay' (tran); du thao 'khong qua 90 ngay'"
        " -> vi_pham (vuot tran)."
        "\n[vi_pham - vuot thoi han luat dinh] Khoan me quy dinh thoi han 'trong thoi han 10 ngay lam viec' (tran);"
        " du thao quy dinh 'trong thoi han 30 ngay lam viec... truong hop vu viec phuc tap co the keo dai them"
        " khong qua 30 ngay' -> vi_pham (30 ngay vuot tran 10 ngay cua luat; du co neu vu viec phuc tap thi"
        " moc thoi han co ban van phai tuan thu luat cap tren). De xuat sua: giam moc co ban ve '10 ngay lam viec'."
        "\n[vi_pham - co_dinh] Khoan me 'vao lop mot la 06 tuoi' (co_dinh); du thao '07 tuoi'"
        " -> vi_pham (doi so lieu co dinh)."
        "\n[vi_pham] Du thao 'bai bo khoan 2 Dieu 107 Bo luat Lao dong' -> vi_pham (vuot tham quyen)."
        "\n[hop_le - tran] Khoan me 'khong qua 48 gio/tuan' (tran); du thao 'khong qua 44 gio/tuan'"
        " -> hop_le (44 <= 48, trong tran). KHONG phai vi pham."
        "\n[hop_le - san] Khoan me 'it nhat 85% luong' (san); du thao 'it nhat 90%'"
        " -> hop_le (90 >= 85, tren san)."
        "\n[hop_le - trao_quyen] Khoan me 'thoi gian thu viec do hai ben thoa thuan' (trao_quyen);"
        " du thao dat 'khong qua 60 ngay' -> hop_le (trong pham vi trao quyen, khop luat)."
        "\n[hop_le] Khoan me 'NLD lam du 12 thang thi duoc nghi hang nam 12 ngay'; du thao 'NLD lam"
        " viec trong dieu kien binh thuong duoc nghi hang nam 12 ngay' -> hop_le. Du thao dien dat"
        " gon, con so 12 ngay KHOP luat, khong he mau thuan; viec khong nhac lai 'du 12 thang'"
        " KHONG lam sai ban chat -> KHONG vi pham."
        "\n[hop_le] Du thao 'to chuc, ca nhan gay o nhiem phai chi tra chi phi xu ly'; Khoan me"
        " 'co quan, to chuc, cong dong dan cu... gay o nhiem phai chi tra, boi thuong'"
        " -> hop_le (noi mot phan doi tuong, khong loai tru ai)."
        "\n[hop_le] Du thao 'Quyet dinh nay co hieu luc tu 01/7/2026' -> hop_le (noi dung hanh chinh)."
        "\n[hop_le] Du thao 'Giam doc So... chiu trach nhiem thi hanh Quyet dinh' -> hop_le (thi hanh)."
        "\n[chua_xac_dinh] Du thao 'phai nop phi bao ve moi truong 03 nam lien tuc truoc khi nop ho so';"
        " cac Khoan me ung vien chi noi ve ho so chung chung, khong Khoan nao quy dinh ve dieu kien"
        " nay -> chua_xac_dinh (noi dung moi, chua co can cu phap ly)."
        "\n[vi_pham - sua toi thieu DUNG] Du thao 'cham nhat 03 ngay lam viec'; can cu CUNG linh vuc,"
        " CUNG chu the, CUNG loai (thoi han) quy dinh '05 ngay lam viec' -> vi_pham; noi_dung_du_thao="
        "'03 ngay', de_xuat_sua='05 ngay' (chi thay con so, giu nguyen chu the & phan con lai)."
        "\n[chua_xac_dinh - khong co can cu noi y chinh] Du thao 'He thong tu dong gui thong bao ket"
        " qua cho cong dan qua tin nhan'; cac Khoan me ung vien chi quy dinh chung ve tiep cong dan,"
        " khong Khoan nao quy dinh viec gui thong bao qua he thong -> chua_xac_dinh. KHONG hop_le chi"
        " vi 'phu hop quy dinh chung / khong trai'."
        "\n[vi_pham - them truong hop vao danh sach dong] Khoan me 'Viec thu hoi giay phep duoc thuc"
        " hien trong cac truong hop sau: a)...; b)...'; du thao 'Ngoai cac truong hop tren, co quan"
        " duoc thu hoi giay phep khi doanh nghiep cham nop bao cao' -> vi_pham (them truong hop ngoai"
        " danh sach dong). KHONG phai chua_xac_dinh du khong Khoan nao noi ve 'cham nop bao cao'."
        "\n[hop_le - cu the hoa trong khuon kho] Khoan me 'co quan, don vi to chuc tap huan tai tru so"
        " cua minh'; du thao cua Bo X 'tap huan tai tru so Cuc A va Cuc B thuoc Bo' -> hop_le (cu the"
        " hoa cho he thong cua Bo X). KHONG vi_pham, va KHONG de xuat thay 'Cuc A, Cuc B' bang danh"
        " sach chung cua Khoan me."
        "\n[chua_xac_dinh - loai can cu khong lien quan] Du thao noi ve chu the/linh vuc A; Khoan me ung vien"
        " noi ve chu the hoac linh vuc KHAC -> LOAI can cu (khong du 3/3 kiem tra lien quan), KHONG"
        " dung no de bat loi; neu khong con can cu dung -> chua_xac_dinh. TUYET DOI khong doi chu the"
        " cua du thao theo can cu khac linh vuc."
        "\n[chua_xac_dinh - khac domain] Trich yeu du thao: 'tiep cong dan, khieu nai, to cao'. Doan"
        " du thao 'Doi tuong ap dung: cong chuc lam nhiem vu tiep cong dan...'; Khoan me ung vien la"
        " 'Doi tuong ap dung' cua mot Thong tu ve QUAN LY THUE (ten_van_ban khac linh vuc) -> LOAI,"
        " tra chua_xac_dinh. KHONG vi_pham du cung cum tu 'Doi tuong ap dung' (trung tu generic)."
        "\n[vi_pham - hanh vi nhay cam, NGOAI LE] Du thao 'cap quyen xem ho so cho nguoi bi to cao, bao"
        " gom ho ten, dia chi cua nguoi to cao'; KHONG Khoan me nao cho phep cong khai danh tinh nguoi"
        " to cao -> vi_pham (tiet lo thong tin ca nhan cua nguoi duoc bao ve, khong co can cu cho phep)."
        " de_xuat_sua: bo 'ho ten, dia chi cua nguoi to cao' khoi pham vi duoc xem."
        "\n[vi_pham - loai bo hinh thuc luat cong nhan] Can cu (du la dieu ve trinh tu/thu tuc) co cum"
        " 'don duoc tiep nhan truc tiep hoac qua dich vu buu chinh' -> luat CONG NHAN 2 hinh thuc do;"
        " du thao 'viec tiep nhan don CHI thuc hien truc tuyen; don buu chinh/truc tiep khong duoc cap"
        " ma ho so' -> vi_pham (loai bo hinh thuc luat cong nhan). can_cu = Khoan co neu hinh thuc do;"
        " de_xuat_sua = cho phep tiep nhan lai don gui truc tiep/qua buu chinh. KHONG tra chua_xac_dinh"
        " chi vi can cu nam trong dieu ve 'phan loai/thu tuc'."
    )
    return [
        {"role": "system", "content": TIER2_KHOAN_HE_THONG + vi_du},
        {"role": "user", "content": (
            (f"VAN BAN DU THAO noi ve (trich yeu): {trich_yeu}\n"
             "-> Dung trich yeu de xac dinh LINH VUC/CHU DE cua doan du thao; LOAI cac Khoan me ung"
             " vien KHAC linh vuc (vd du thao ve tiep cong dan/khieu nai-to cao ma can cu ve tai"
             " chinh/thue/xay dung...) theo quy tac KIEM TRA LIEN QUAN.\n\n" if trich_yeu else "")
            + "Doan du thao can tham dinh:\n" + str(doan_du_thao) + "\n\n"
            "Cac Khoan me ung vien (semantic search, co ngu canh truoc/sau neu co):\n"
            + str(khoan_ung_vien) + "\n\n"
            "Lam theo QUY TRINH 3 BUOC va TU KIEM TRA. MOT doan co the co NHIEU loi DOC LAP"
            " (vd vua thu hep hinh thuc, vua dat nghia vu trai luat): ghi loi CHINH (nghiem trong nhat)"
            " o cac truong duoi, cac loi con lai cho vao 'cac_loi_them' (mang; [] neu chi 1 loi), moi"
            " loi 1 phan tu rieng snippet/can cu/giai thich. Tra DUNG 1 object JSON (khong markdown):"
            '\n{"trang_thai": "vi_pham|hop_le|chua_xac_dinh",'
            ' "can_cu": {"khoan_id": "<id Khoan me lien quan, rong neu chua_xac_dinh>",'
            ' "trich_dan": "<nguyen van Khoan me, rong neu chua_xac_dinh>"},'
            ' "noi_dung_du_thao": "<CHI khi vi_pham: CHEP CHINH XAC tung chu doan SAI'
            ' nam trong doan du thao - CHI phan sai thoi, KHONG chep lai ca doan vi dai va thua>",'
            ' "giai_thich": "<ly do ngan gon, neu ro diem khac biet neu vi_pham>",'
            ' "cac_loi_them": [{"khoan_id": "<id that trong ung vien>", "trich_dan": "<nguyen van khoan>",'
            ' "noi_dung_du_thao": "<phan sai KHAC voi loi chinh>", "giai_thich": "<ly do>"}],'
            ' "tin_cay": 0.0}'
        )},
    ]


DE_XUAT_SUA_HE_THONG = HE_THONG_CHUNG + """
Nhiệm vụ: Bạn là chuyên gia pháp chế soạn thảo văn bản quy phạm pháp luật Việt Nam.
Một đoạn trong văn bản dự thảo ĐÃ ĐƯỢC XÁC ĐỊNH LÀ VI PHẠM (hoặc mâu thuẫn/không phù hợp) với một CĂN CỨ PHÁP LÝ cụ thể.
Nhiệm vụ: Suy luận chi tiết về điểm xung đột và VIẾT LẠI ĐỀ XUẤT SỬA ĐỔI để đoạn dự thảo hoàn toàn phù hợp với căn cứ pháp lý và đúng quy chuẩn ngôn ngữ lập pháp.

QUY TẮC BẮT BUỘC:
1. SỬA TỐI THIỂU: 'de_xuat_sua' là chuỗi THAY THẾ TRỰC TIẾP cho 'noi_dung_sai' (hoặc đoạn dự thảo). Sửa đúng chỗ sai, giữ nguyên phạm vi; không viết lại cả đoạn dài nếu chỉ sai một cụm từ, con số, hoặc một điểm/khoản.
2. BẢO TOÀN CHỦ THỂ & BỐI CẢNH: Giữ nguyên chủ thể, hệ thống cơ quan, đối tượng và văn cảnh của cơ quan ban hành dự thảo. TUYỆT ĐỐI không thay thế chủ thể của dự thảo bằng chủ thể thuộc cơ quan khác của văn bản luật cấp trên.
3. KHÔNG VIẾT HƯỚNG DẪN / MỆNH LỆNH: Tuyệt đối KHÔNG viết 'Sửa X thành Y', 'Cần bỏ...', 'Nên thay...'. CHỈ trả về đúng văn bản hoàn chỉnh sau khi sửa.
   Ví dụ:
   - Sai: 'trong thời hạn 30 ngày làm việc' -> de_xuat_sua: 'trong thời hạn 10 ngày làm việc'
   - Sai: 'ít nhất 70%' -> de_xuat_sua: 'ít nhất 85%'
   - Sai (thêm trường hợp ngoài danh sách đóng): loại bỏ trường hợp tự thêm đó.
4. CĂN CỨ CÓ SỬA ĐỔI: Nếu căn cứ có khối quy định sau sửa đổi/bổ sung, phải sửa theo quy phạm mới nhất sau khi sửa đổi, không sửa theo bản cũ.
5. CHUẨN XÁC VĂN PHONG LẬP PHÁP: Ngắn gọn, chặt chẽ, đúng quy tắc văn bản quy phạm pháp luật Việt Nam.

ĐỊNH DẠNG TRẢ LỜI: CHỈ trả 1 object JSON thuần túy (không markdown):
{"giai_thich": "<phân tích sắc sảo lý do vi phạm và giải pháp khắc phục>", "de_xuat_sua": "<chuỗi văn bản thay thế hoàn chỉnh sau khi sửa>"}
"""


def prompt_tier2_de_xuat(
    doan_du_thao: dict,
    can_cu: dict,
    snippet_sai: str = "",
    ly_do_so_bo: str = "",
    trich_yeu: str = "",
) -> list[dict[str, str]]:
    """Prompt tier2 Pass 2: suy luan va de xuat sua cho doan da xac dinh vi pham (think=True)."""
    nd_sai = snippet_sai.strip() or doan_du_thao.get("noi_dung", "")
    cc_rut_gon = {
        "so_hieu": can_cu.get("so_hieu", ""),
        "ten_van_ban": can_cu.get("ten_van_ban", ""),
        "so_dieu": can_cu.get("so_dieu"),
        "so_khoan": can_cu.get("so_khoan"),
        "diem": can_cu.get("diem"),
        "tieu_de_dieu": can_cu.get("tieu_de_dieu", ""),
        "noi_dung": (can_cu.get("noi_dung") or "")[:2500],
    }
    user_content = (
        (f"VAN BAN DU THAO noi ve (trich yeu): {trich_yeu}\n\n" if trich_yeu else "")
        + f"DOAN DU THAO:\n{doan_du_thao.get('noi_dung', '')}\n\n"
        + f"PHAN NOI DUNG XAC DINH VI PHAM (can sua):\n{nd_sai}\n\n"
        + f"CAN CU PHAP LY BI VI PHAM:\n{str(cc_rut_gon)}\n\n"
        + (f"GHI CHU VI PHAM SO BO:\n{ly_do_so_bo}\n\n" if ly_do_so_bo else "")
        + "Hay suy luan chi tiet va tra JSON: {'giai_thich': '...', 'de_xuat_sua': '...'}"
    )
    return [
        {"role": "system", "content": DE_XUAT_SUA_HE_THONG},
        {"role": "user", "content": user_content},
    ]


def prompt_tier2(
    dieu_du_thao: dict, dieu_me_list: list[dict], cap_du_thao: int | None, cap_me_cao_nhat: int | None,
) -> list[dict[str, str]]:
    thong_tin_cap = ""
    if cap_du_thao is not None and cap_me_cao_nhat is not None:
        thong_tin_cap = f"\nCap du thao = {cap_du_thao}, cap me cao nhat = {cap_me_cao_nhat}.\n"
    return [
        {"role": "system", "content": TIER2_HE_THONG},
        {"role": "user", "content": (
            "Dieu du thao (du Khoan):\n" + str(dieu_du_thao) + "\n\n"
            "Cac Dieu me duoc anh xa (nguyen van, co ghi 'da sua boi' neu co):\n" + str(dieu_me_list) + "\n"
            + thong_tin_cap +
            "\nTra JSON mang [{so_khoan_du_thao, loai_loi, muc_do, tin_cay, "
            "can_cu:{dieu_me_id, so_khoan, trich_dan}, giai_thich, de_xuat_sua}]. "
            f"loai_loi thuoc: {LOAI_LOI_TIER2}. muc_do thuoc cao|trung_binh|thap. "
            "tin_cay 0..1. phu_hop khong ghi vao DB nhung co the de nghi so sanh."
        )},
    ]
