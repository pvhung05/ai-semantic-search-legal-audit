---
name: legal-audit-workflow
description: Luồng đối chiếu dự thảo với kho pháp luật theo cây thẩm quyền của audit_rag - segment, xác định văn bản mẹ, tier1 xác định, ánh xạ Điều bằng LLM, tier2 so sánh cặp, fallback, workflow dừng/duyệt/tiếp tục, prompt JSON, validate căn cứ, cache, báo cáo, API audit, eval. Dùng skill này mỗi khi làm việc trong app/audit/, app/api/routes_audit.py, scripts/audit.py, scripts/eval_audit.py, khi viết hoặc sửa prompt, khi người dùng nói "đối chiếu", "phát hiện", "căn cứ pháp lý", "ánh xạ", "văn bản mẹ", "tier1", "tier2", "báo cáo audit".
---

# Luồng đối chiếu theo cây thẩm quyền

Ý tưởng: dự thảo chỉ có thể trái với một **tập văn bản mẹ** nhỏ xác định được trước. Nên không tìm kiếm ngữ nghĩa trên toàn kho; thay vào đó xác định văn bản mẹ, ánh xạ Điều với Điều rồi cho LLM đọc nguyên văn hai bên. Mọi phát hiện phải có **căn cứ là bản ghi thật** trong DB, trích được nguyên văn.

## Các bước và trạng thái phiên

```
tao → [parent_docs] → cho_duyet_vb_me → [tier1] → [mapping] → cho_duyet_anh_xa → [tier2 ∥ fallback] → xong
```

`phien_doi_chieu.buoc` lưu sau mỗi bước. `workflow.chay(phien_id)` đọc `buoc` và chạy **đúng bước kế tiếp**, rồi dừng nếu bước đó là điểm duyệt và `tu_dong_duyet=false`. API `POST /audit/{id}/tiep-tuc` gọi lại `chay`. Không bước nào chạy lại việc bước trước đã làm (tier1 không chạy lại khi tiếp tục từ `cho_duyet_anh_xa`).

Mỗi bước là một module với một hàm vào, nhận phụ thuộc qua tham số (xem skill `clean-code-solid`):

| Bước | Hàm | Phụ thuộc | Ghi |
|---|---|---|---|
| segment | `tach_don_vi(text, loai) -> SegmentResult` | parser, LLM (gom cụm, tùy chọn) | `tai_lieu_don_vi`, `tai_lieu.can_cu_tho` |
| parent_docs | `xac_dinh_van_ban_me(tai_lieu, ngay, reader) -> list[VanBanMe]` | repo_van_ban, repo_hieu_luc | `phien_van_ban_me`, `tai_lieu.loai_cay` |
| consolidate | `lay_muc_luc_me(vb_ids, ngay, reader) -> list[MucLucDieu]` | `ban_hop_nhat` | — (in-memory) |
| tier1 | `Tier1.chay(don_vis, ngay) -> list[PhatHien]` | checks (dẫn chiếu, nguyên văn, thể thức) | `ket_qua_doi_chieu` tang=1, `dan_chieu(nguon='tai_lieu')` |
| mapping | `anh_xa_dieu(muc_luc_du_thao, muc_luc_me, llm, max) -> list[AnhXa]` | LLM | `anh_xa_dieu` |
| tier2 | `so_sanh_cap(dieu_du_thao, dieu_me_list, llm) -> list[PhatHien]` | LLM, cache | `ket_qua_doi_chieu` tang=2 |
| fallback | `xu_ly_mo_coi(dieu, ...)` | retriever (GĐ E) hoặc không | tang=3 hoặc `khong_co_can_cu_uy_quyen` |
| report | `tao_bao_cao(phien) -> str` | repo_audit | markdown |

## Xác định văn bản mẹ

Thứ tự nguồn, ghi `nguon` tương ứng, dừng khi `loai_cay='ro'`:
1. `can_cu`: khớp `can_cu_tho` với `van_ban` theo số hiệu, rồi tên + năm (chuẩn hóa chữ thường, bỏ "năm"). Không khớp → giữ trong `can_cu_tho`, WARNING, không bỏ.
2. `quan_he`: `van_ban_me_qua_do_thi(ids)` → thêm với `buoc_sau`.
3. `dan_chieu`: văn bản được dẫn ≥ 2 lần trong đơn vị mà chưa có.
4. `chu_de`: `chu_de_van_ban_me(loai_tai_lieu, linh_vuc)`.
5. `truy_hoi`: chỉ khi `ENABLE_FALLBACK`.

Luật nền thêm tự động với cờ `chi_tier1=true` (không ánh xạ): có từ "xử phạt/phạt tiền" → Luật XLVPHC; `loai` là dự thảo VBQPPL → Luật Ban hành VBQPPL. `loai_cay`: `ro` (có từ 1–2), `mo` (chỉ 3–5), `khong` (rỗng → `buoc='cho_duyet_vb_me'` với danh sách trống, người dùng chọn tay).

Bản hợp nhất lấy tại `ngay` của phiên; văn bản mẹ > 300 Điều → mục lục chia theo Chương, mapping gọi nhiều lần và hợp kết quả.

## Tier1 (không LLM)

Chạy trên **mọi** đơn vị cấp khoản/đoạn, trước mapping, kết quả `tin_cay=1.0`:
- Dẫn chiếu → `khoan_hieu_luc_tai`/`dieu_hieu_luc_tai` tại ngày → `ket_qua` → `loai_loi`: `dan_chieu_khong_ton_tai | dan_chieu_sai_so_hieu | dan_het_hieu_luc | dan_bi_bai_bo | dan_chua_hieu_luc`. Với `dan_het_hieu_luc` căn cứ là **bản mới** còn hiệu lực + ghi rõ văn bản sửa trong `giai_thich`.
- Nguyên văn: đoạn trong ngoặc kép hoặc sau "quy định:" gắn với dẫn chiếu gần nhất → `rapidfuzz.fuzz.ratio(normalize(a), normalize(b)) < AUDIT_DIFF_NGUONG*100` → `trich_sai_nguyen_van`, `giai_thich` chứa diff ngắn (từ khác nhau).
- Thể thức: số hiệu trong Căn cứ có loại/cơ quan không khớp DB → `the_thuc`.

Thêm loại kiểm tra = thêm một `Checker` vào `tier1/checks/`, đăng ký trong `tao_tier1`.

## Mapping (LLM, một lần)

- Input: `[{id, so_dieu, tieu_de, mo_dau(≤2 câu)}]` dự thảo và `[{dieu_id, ten_vb, so_dieu, tieu_de, tom_tat}]` mẹ.
- Output: `[{don_vi_id, dieu_me_ids: [], loai: cu_the_hoa|cung_chu_de, tin_cay}]`; rỗng = mồ côi.
- Validate: mọi id ∈ input (loại và log id lạ); tối đa `AUDIT_MAX_DIEU_ME`, vượt → giữ tin cậy cao nhất, phần còn lại `loai='cung_chu_de'` (báo cáo liệt kê, tier2 không xét).
- Bổ sung không LLM: Điều dự thảo dẫn thẳng Điều mẹ → `nguon='dan_chieu'`, `tin_cay=1.0`.
- `hash_cap = sha256(don_vi.hash | dieu_me_id | ngay)` ghi vào mỗi dòng.

## Tier2 (LLM, mỗi Điều dự thảo một lần)

- Prompt gồm: Điều dự thảo nguyên văn (đủ Khoản, có số), từng Điều mẹ nguyên văn kèm `ten_vb`, `cap`, "đã sửa bởi X, hiệu lực Y" nếu `da_sua`, và `cap_tuong_duong` của dự thảo.
- Output: `[{so_khoan_du_thao, loai_loi, muc_do, tin_cay, can_cu: {dieu_me_id, so_khoan, trich_dan}, giai_thich, de_xuat_sua}]`; `loai_loi ∈ phu_hop | thu_hep_pham_vi | mo_rong_pham_vi | them_dieu_kien | them_nghia_vu | doi_so_lieu | dat_thu_tuc_moi | mau_thuan_truc_tiep | vuot_tham_quyen`.
- Validate theo thứ tự: parse JSON → pydantic → `dieu_me_id` ∈ ánh xạ đã duyệt → `trich_dan` khớp Điều mẹ (`fuzz.partial_ratio ≥ 85` sau normalize; không khớp → `tin_cay = min(tin_cay, 0.5)`, ghi chú "trích dẫn không khớp nguyên văn") → phân giải `can_cu_khoan_id` từ `so_khoan` (không ra → để NULL, giữ `can_cu_dieu_id`) → `vuot_tham_quyen` chỉ khi `cap_tuong_duong > cap mẹ`, ngược lại đổi `mau_thuan_truc_tiep`.
- `phu_hop` không ghi DB, chỉ đếm vào `thong_ke.so_khoan_phu_hop`.
- Cache `tier2_cache(hash_cap, cau_hinh_hash)` với `cau_hinh_hash = sha256(LLM_MODEL | prompt_version)`. Phiên bản 2 của tài liệu chỉ gọi LLM cho cặp chưa cache.
- Song song theo Điều với `asyncio.Semaphore(LLM_SONG_SONG)`; cộng `thong_ke.so_goi_llm`.

## Fallback

`ENABLE_FALLBACK=false` (mặc định demo): Điều mồ côi → một phát hiện `khong_co_can_cu_uy_quyen`, `muc_do='trung_binh'`, `tin_cay=0.6`, `giai_thich="Không ánh xạ được tới Điều nào của văn bản mẹ; cần rà soát thủ công"`, không căn cứ. Khi bật: embed từng khoản → `tim_kiem_hybrid(p_cap_max = cap_tuong_duong - 1)` → ứng viên ≥ `AUDIT_NGUONG_FALLBACK` → ánh xạ `nguon='truy_hoi'` → tier2 `tang=3`.

## Prompt (`audit/prompts.py`, `PROMPT_VERSION` hằng số)

- Tiếng Việt; system: "Bạn là chuyên viên thẩm định văn bản quy phạm pháp luật. Chỉ trả JSON hợp lệ, không giải thích ngoài JSON."
- Nêu rõ schema output, 1–2 ví dụ ngắn, quy tắc: "chỉ kết luận khi trích được nguyên văn căn cứ; không chắc → phu_hop với tin_cay thấp".
- `temperature ≤ 0.1`, tắt thinking (`LLM_DISABLE_THINKING`). Cắt ``` trước parse; lỗi parse → retry 1 lần kèm thông báo lỗi; vẫn lỗi → `LLMOutputError`, phiên `buoc='loi'` với `loi` ghi rõ Điều nào.
- Prompt là hàm thuần trả chuỗi; test prompt bằng snapshot (so sánh với file `tests/audit/snapshots/*.txt`).

## Báo cáo (`report.py`) – thứ tự cố định

1. Thông tin phiên (tài liệu, ngày tra, chế độ, thống kê).
2. Văn bản mẹ (nguồn suy ra, duyệt).
3. Bảng ánh xạ Điều ↔ Điều mẹ (kèm `cung_chu_de` riêng).
4. Phát hiện theo Điều dự thảo, mỗi mục: vị trí, loại, mức, tin cậy, **căn cứ** (văn bản – Điều – Khoản, hiệu lực, trích nguyên văn), đoạn dự thảo, giải thích, đề xuất, cờ `can_ra_soat` nếu có.
5. Điều mồ côi.
6. Phụ lục: dẫn chiếu hợp lệ đã kiểm.

## API (`routes_audit.py`)

`POST /audit` → tạo phiên, chạy tới điểm dừng đầu; `GET /audit/{id}` trả `buoc` + dữ liệu bước hiện tại (danh sách VB mẹ hoặc ánh xạ hoặc kết quả); `PUT .../van-ban-me`, `PUT .../anh-xa` chỉ hợp lệ khi `buoc` tương ứng (sai → 409 `AuditStateError`); `POST .../tiep-tuc`; `GET .../ket-qua?loai_loi=&muc_do=`; `PATCH /audit/ket-qua/{id}` (`xac_nhan|bac_bo`); `GET .../report.md`. Worker nền chạy `chay(phien_id)`; API không block.

## Eval (`scripts/eval_audit.py`)

Ba chỉ số riêng: (1) ánh xạ: tỷ lệ Điều có ≥ 1 `dieu_me_mong_doi` đúng, tỷ lệ mồ côi giả; (2) tier1: recall theo loại, false positive trên mẫu âm; (3) tier2: recall/precision theo loại. Ca tiêm lỗi từ Điều thật (đổi số liệu, thêm điều kiện, đảo được/không được, đặt thủ tục mới, trích sai, dẫn Điều đã sửa/bãi bỏ/không tồn tại), mỗi loại ≥ 6, mẫu âm ≥ 10. Ghi `eval_run`; bảng vào README.

Ví dụ prompt và JSON vào/ra: `references/vi-du-prompt.md`.
