# Ví dụ prompt và JSON (nội dung luật là minh họa)

## Mapping

**System**
```
Bạn là chuyên viên thẩm định văn bản quy phạm pháp luật. Chỉ trả JSON hợp lệ, không giải thích ngoài JSON.
```

**User**
```
Nhiệm vụ: với mỗi Điều của DỰ THẢO, liệt kê các Điều của VĂN BẢN MẸ mà nó quy định chi tiết, hướng dẫn,
hoặc cùng điều chỉnh một nội dung. Chỉ dùng dieu_id có trong danh sách VĂN BẢN MẸ. Không có → dieu_me_ids rỗng.
Tối đa 6 dieu_me cho một Điều. loai = "cu_the_hoa" nếu Điều dự thảo hướng dẫn trực tiếp, "cung_chu_de" nếu chỉ cùng nội dung.

DỰ THẢO:
[{"id":"TL-a1:D5","so_dieu":"5","tieu_de":"Thời hạn thông báo khi hết hạn hợp đồng","mo_dau":"Người sử dụng lao động phải thông báo..."},
 {"id":"TL-a1:D12","so_dieu":"12","tieu_de":"Quỹ hỗ trợ nội bộ","mo_dau":"Doanh nghiệp lập quỹ..."}]

VĂN BẢN MẸ:
[{"dieu_id":"BLLD-2019-45:D45","ten_vb":"Bộ luật Lao động 2019","so_dieu":"45","tieu_de":"Thông báo chấm dứt hợp đồng lao động","tom_tat":"Nghĩa vụ thông báo bằng văn bản khi chấm dứt hợp đồng."},
 {"dieu_id":"ND-2020-145:D13","ten_vb":"Nghị định 145/2020","so_dieu":"13","tieu_de":"Thời hạn thông báo","tom_tat":"Quy định thời hạn và hình thức thông báo chấm dứt."},
 ...]

Trả về: [{"don_vi_id":"...","dieu_me_ids":["..."],"loai":"cu_the_hoa","tin_cay":0.0-1.0}]
```

**Output mong đợi**
```json
[{"don_vi_id":"TL-a1:D5","dieu_me_ids":["BLLD-2019-45:D45","ND-2020-145:D13"],"loai":"cu_the_hoa","tin_cay":0.9},
 {"don_vi_id":"TL-a1:D12","dieu_me_ids":[],"loai":"cu_the_hoa","tin_cay":0.0}]
```
→ `TL-a1:D12` là mồ côi → `khong_co_can_cu_uy_quyen`.

## Tier2

**User** (rút gọn)
```
DỰ THẢO (Thông tư, cấp 7) – Điều 5. Thời hạn thông báo khi hết hạn hợp đồng
1. Người sử dụng lao động phải thông báo bằng văn bản cho người lao động chậm nhất 05 ngày làm việc trước khi hết hạn hợp đồng.
2. Việc thông báo chỉ áp dụng với hợp đồng có thời hạn từ 12 tháng trở lên.

VĂN BẢN MẸ 1 – Nghị định 145/2020 (cấp 5), Điều 13 (đã sửa bởi NĐ 12/2026, hiệu lực 01/03/2026):
1. ... thông báo bằng văn bản ... chậm nhất 15 ngày trước ngày hợp đồng hết hạn.
2. Áp dụng với mọi hợp đồng lao động xác định thời hạn.

Với từng Khoản của Điều dự thảo, so với từng văn bản mẹ, trả JSON mảng:
{"so_khoan_du_thao","loai_loi","muc_do","tin_cay","can_cu":{"dieu_me_id","so_khoan","trich_dan"},"giai_thich","de_xuat_sua"}
loai_loi ∈ phu_hop|thu_hep_pham_vi|mo_rong_pham_vi|them_dieu_kien|them_nghia_vu|doi_so_lieu|dat_thu_tuc_moi|mau_thuan_truc_tiep|vuot_tham_quyen.
Chỉ kết luận khi trích được nguyên văn căn cứ trong văn bản mẹ; không chắc → phu_hop với tin_cay thấp.
```

**Output mong đợi**
```json
[
 {"so_khoan_du_thao":"1","loai_loi":"doi_so_lieu","muc_do":"cao","tin_cay":0.95,
  "can_cu":{"dieu_me_id":"ND-2020-145:D13@2026-03-01","so_khoan":"1","trich_dan":"chậm nhất 15 ngày trước ngày hợp đồng hết hạn"},
  "giai_thich":"Dự thảo quy định 05 ngày làm việc, văn bản mẹ quy định 15 ngày.",
  "de_xuat_sua":"Sửa thành 'chậm nhất 15 ngày trước ngày hợp đồng hết hạn'."},
 {"so_khoan_du_thao":"2","loai_loi":"thu_hep_pham_vi","muc_do":"cao","tin_cay":0.9,
  "can_cu":{"dieu_me_id":"ND-2020-145:D13@2026-03-01","so_khoan":"2","trich_dan":"Áp dụng với mọi hợp đồng lao động xác định thời hạn"},
  "giai_thich":"Dự thảo giới hạn ở hợp đồng từ 12 tháng, văn bản mẹ áp dụng với mọi hợp đồng xác định thời hạn.",
  "de_xuat_sua":"Bỏ điều kiện 12 tháng."}
]
```

Sau validate: `can_cu_khoan_id = 'ND-2020-145:D13:K1@2026-03-01'` (phân giải từ so_khoan tại ngày), `can_cu_tin_cay` kế thừa từ khoản. Nếu `trich_dan` không khớp nguyên văn Điều mẹ (partial_ratio < 85) → `tin_cay` 0.5 và ghi chú trong `giai_thich`.
