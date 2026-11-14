# Ràng buộc — luồng audit (`so_sanh.py`, `prompts.py`, `validate.py`)

Đầu ra của luồng này là kết luận pháp lý trả cho người soạn thảo. Sai theo hướng "báo vi phạm giả" hoặc "sửa dự thảo theo luật khác lĩnh vực" tệ hơn trả `CHUA_XAC_DINH`.

## Hợp đồng đầu ra (không được phá)

1. Luồng audit chạy cascade 2-pass:
   - **Pass 1** (`prompt_tier2_khoan`, mặc định `think=False`): phân loại nhanh `trang_thai` (`vi_pham`, `hop_le`, `chua_xac_dinh`), `can_cu{khoan_id, trich_dan}`, `can_cu_vi_pham_ids[]`, `noi_dung_du_thao` (snippet sai), `giai_thich` sơ bộ, `tin_cay`.
   - **Pass 2** (`prompt_tier2_de_xuat`, mặc định `think=True`): chỉ chạy cho các mục `VI_PHAM`, gom TẤT CẢ các căn cứ bị vi phạm trong 1 lượt gọi duy nhất mỗi đơn vị để suy luận sâu và sinh đề xuất sửa giải quyết đồng thời mọi vi phạm.
   - Đầu ra cuối cùng của `so_sanh.chay_tier2` phải giữ đầy đủ các khóa: `trang_thai`, `doan_du_thao`, `so_hieu`, `ten_van_ban`, `trich_dan`, `giai_thich`, `de_xuat_sua`, `tin_cay`, `tac_dong`, `cc_vi_tri`. Đổi khóa nào thì sửa cả UI (`api/static/index.html`) và `docx_track.py` trong cùng commit.
2. Mọi verdict đi qua `_chuan_hoa_trang_thai`: chuỗi lạ → `CHUA_XAC_DINH`. Không thêm trạng thái thứ 4.
3. `can_cu.khoan_id` phải thuộc tập ứng viên đã đưa vào prompt; không khớp thì code lấy ứng viên đầu (hành vi hiện tại, xem mục Biết là còn thiếu).
4. `noi_dung_du_thao` chỉ được dùng nếu `la_snippet_hop_le` (là chuỗi con thật, ngắn hơn đoạn gốc); ngược lại dùng nguyên đoạn. `de_xuat_sua` phải là **chuỗi thay thế trực tiếp** cho snippet (không phải câu mệnh lệnh "sửa X thành Y") — `cat_theo_pham_vi` và DOCX track-change dựa vào điều này.
5. Lỗi gọi LLM của một đơn vị → log WARNING, bỏ đơn vị đó; không làm hỏng cả request.

## Quy tắc phán quyết (đã mã hóa trong prompt — giữ khi sửa prompt)

- `hop_le` chỉ khi có căn cứ **thực sự nói ý đó**; "không trái" là chưa đủ → `chua_xac_dinh`.
- Số liệu so theo loại ràng buộc của căn cứ (`loai_rang_buoc`: sàn / trần / cố định / trao quyền, tính trong `retrieval/can_cu.py`).
- Thêm trường hợp vào danh sách đóng của luật = vi phạm. Cụ thể hóa cho hệ thống cơ quan của mình = hợp lệ.
- Loại căn cứ khác lĩnh vực/chủ thể (dùng `trich_yeu`); **không bao giờ** "sửa" dự thảo bằng cách thay chủ thể của nó bằng chủ thể của luật khác.
- Căn cứ đã bị sửa đổi → so với nội dung sau sửa; đã hết hiệu lực → không dùng làm cơ sở.

## Khi sửa prompt

- **Hỗ trợ 2 bộ prompt chuyên biệt cho Local LLM và Public LLM**:
  + **Local LLM (Qwen3:14b qua Ollama, `IS_LOCAL=true`)**: dùng `prompt_tier2_khoan` và `prompt_tier2_de_xuat` với tập few-shot ví dụ cụ thể, định dạng gọn gàng để kiểm soát chặt chẽ model local.
  + **Public LLM (Gemini, Claude, GPT, `IS_LOCAL=false` hoặc request `is_local=False`)**: dùng `prompt_tier2_khoan_public` và `prompt_tier2_de_xuat_public`. Thiết kế tiếng Việt có dấu 100%, cấu trúc phân cấp Markdown rõ ràng, và quan trọng nhất: **đặt trường `giai_thich` TRƯỚC `trang_thai` trong JSON schema** để ép mô hình thực hiện Chain-of-Thought (suy luận logic) trước khi chốt nhãn kết luận, tránh phán quyết vội vã.
- Chưa có bộ eval cho luồng này (`scripts/eval_audit.py` chỉ đo workflow di sản). Mọi thay đổi prompt/tham số retrieval hiện chỉ kiểm tay trên dự thảo mẫu. Ghi rõ ca đã thử vào commit message hoặc `PROGRESS.md`.

## Biết là còn thiếu (đừng tưởng đã có)

- **Không kiểm `trich_dan` có khớp nguyên văn căn cứ.** LLM có thể bịa trích dẫn mà không bị phát hiện. Hướng đã thống nhất: `rapidfuzz.partial_ratio ≥ 85` với căn cứ đã đưa vào prompt, không đạt → hạ `CHUA_XAC_DINH`. Đây là việc ưu tiên số 1 trong [PROGRESS.md](../../../PROGRESS.md).
