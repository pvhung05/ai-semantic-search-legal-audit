# PROGRESS

Cập nhật cuối mỗi phiên làm việc (xem quy tắc trong [AGENTS.md](AGENTS.md)). Ghi ngày tuyệt đối.

## Đã xong

- Crawler vbpl.vn (Server Action + RSC), schema metadata, catalog, cây nội dung, tác động cấp điều khoản — `app/crawl`.
- Kho luật dạng cây `node` + `chunk` (node lá có ngữ cảnh cha), embedding bge-m3, tách 3 schema `danhmuc`/`vanban`/`rag` (migration 003–017).
- Tách 2 service `crawl` / `doisanh` dùng chung `core`.
- Truy hồi lai (vector + BM25 + RRF trong SQL) → rerank TEI → gộp anh em lên Khoản/Điều; gắn nội dung sau sửa đổi vào căn cứ.
- `/audit` stateless (3 nhóm VI_PHAM / HOP_LE / CHUA_XAC_DINH) + DOCX track-change; `/ask` có dẫn chiếu và nhớ lịch sử; UI xem toàn văn HTML vbpl.
- 13/11/2026: harness tài liệu cho agent (`AGENTS.md`, `ARCHITECTURE.md`/`CONSTRAINTS.md` theo module, `tasks.py`).

## Đang làm

- **Tinh chỉnh để Qwen3:14b (model chính) phát hiện lỗi và đề xuất sửa đoạn dự thảo tốt hơn** — `app/doisanh/audit/prompts.py`, `so_sanh.py`: đã tách cascade 2-pass (Pass 1 phân loại nhanh `think=False`, Pass 2 suy luận sâu `think=True` sinh đề xuất sửa cho các mục vi phạm).
  - Dự thảo mẫu để kiểm tay và 5 ca thử nằm ở đâu (`data/` bị `.gitignore`): TODO: cần xác nhận.

## Bị chặn

- Không có.

## Tiếp theo (thứ tự ưu tiên đã xác nhận)

1. **Kiểm trích dẫn nguyên văn** trong `so_sanh.py`: `rapidfuzz.partial_ratio(trich_dan, căn cứ đã đưa vào prompt) ≥ 85`, không đạt → hạ `CHUA_XAC_DINH`. Chi tiết: [app/doisanh/audit/CONSTRAINTS.md](app/doisanh/audit/CONSTRAINTS.md).
2. **Bộ đánh giá có nhãn** cho luồng hiện tại: dữ liệu (đoạn dự thảo → verdict + căn cứ đúng) từ dự thảo thật đã được người duyệt; viết lại `scripts/eval_audit.py` cho `chay_tier2`; chạy mỗi khi đổi prompt / model / tham số retrieval.
3. **Dọn mã di sản** (danh sách trong [app/doisanh/ARCHITECTURE.md](app/doisanh/ARCHITECTURE.md)). Port hay xóa từng nhóm: TODO: cần xác nhận.

Đã quyết định nhưng chưa xếp thứ tự:
- **Đổi tên toàn bộ code sang tiếng Anh** (hàm, biến, module; quyết định 13/11/2026, chưa bắt đầu). Làm thành đợt riêng, theo từng module, mỗi module một commit, `python tasks.py check` xanh sau mỗi bước; cập nhật tài liệu module trong cùng commit. Vị trí trong thứ tự ưu tiên: TODO: cần xác nhận.

Ý tưởng, chưa quyết: tách từ tiếng Việt cho BM25 (hiện `tsvector` cấu hình `simple`) nếu đo được recall thấp.

## Mốc thời gian

- Hạn nộp / bảo vệ KLTN: TODO: cần xác nhận.

## Nhật ký phiên

- 13/11/2026 — branch `feat/ai-agent`: định dạng hiển thị căn cứ trên UI (`index.html`): tự động xuống dòng và thụt lề theo cấu trúc Chương, Điều, Khoản (1., 2...), Điểm (a, b...) và phân tách nhiều căn cứ (`---`).
- 13/11/2026 — branch `feat/ai-agent`: nâng cấp Pass 2 gom toàn bộ các căn cứ vi phạm trong 1 lượt gọi duy nhất mỗi đơn vị dự thảo (`can_cu_vi_pham_ids`), LLM suy luận tổng thể khắc phục đồng thời các vi phạm, bổ sung unit test `test_chay_tier2_multiple_violating_bases_single_call`.
- 13/11/2026 — branch `feat/ai-agent`: tách luồng audit thành cascade 2-pass (Pass 1 phân loại nhanh `think=False`, Pass 2 suy luận sâu `think=True` cho các mục vi phạm để sinh đề xuất sửa); bổ sung `prompt_tier2_de_xuat`, cập nhật `so_sanh.py`, test `test_so_sanh_cascade.py` và cập nhật tài liệu module.
- 13/11/2026 — branch `feat/ai-agent`: rà soát toàn bộ import và dependency trong `@app`, hoàn thiện `requirements.txt` và `pyproject.toml` (bổ sung `lxml`, `python-dotenv`, `PyYAML`; đồng bộ version pin theo `.venv` chuẩn).
- 13/11/2026 — branch `docs/agent-harness`: thêm tài liệu agent, `tasks.py`, kiểm tra tài liệu; cập nhật skill `.claude/skills/` theo cấu trúc hiện tại.
- 13/11/2026 — sửa crawl `doc_info` hỏng do vbpl đổi format (`</html>1:` → `</body>1:`), commit `8d5f10d`. 72 mục `crawl_queue` lỗi `Extra data…` cần reset `so_lan_thu` để crawl lại (mục đã đủ 3 lần thử sẽ không được `take_pending` lấy lại).
