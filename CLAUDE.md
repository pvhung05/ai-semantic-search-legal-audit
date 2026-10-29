# audit_rag – hướng dẫn cho Claude Code

Dự án: service đối chiếu văn bản dự thảo với kho pháp luật Việt Nam (PostgreSQL + pgvector, FastAPI, LLM qua HTTP). Kế hoạch chi tiết ở `PLAN.md` (v3). **Không dùng LlamaIndex/LangChain.**

## Trước mỗi task
1. Đọc `PLAN.md` mục 1 (cách tiếp cận), 4 (schema), 6 (quy ước); tìm task trong mục 7.
2. Mở skill tương ứng trong `.claude/skills/` (được nạp tự động theo mô tả):
   - `clean-code-solid` – chuẩn code, kiến trúc, test: áp dụng cho **mọi** task.
   - `legal-db-schema` – khi chạm DB, SQL, hiệu lực, phiên bản.
   - `vn-law-parser` – khi chạm `app/ingestion/`, regex văn bản luật, dẫn chiếu, lệnh sửa đổi.
   - `legal-audit-workflow` – khi chạm `app/audit/`, prompt, báo cáo, API audit.
3. Môi trường: `.venv`, Python 3.10+, `.env` từ `.env.example`; DB `python scripts/init_db.py`.

## Luật bất di bất dịch
- Không bịa nội dung luật, không tự chế văn bản để test. Thiếu dữ liệu thật → dừng và hỏi.
- Không sửa migration đã áp dụng; không đổi tên bảng/cột.
- Mọi phát hiện đối chiếu phải có căn cứ là bản ghi thật trong DB.
- Mỗi task một commit `GĐ<X><n> <module>: <việc>`; test đi cùng code; cập nhật `PLAN.md` mục 10.
