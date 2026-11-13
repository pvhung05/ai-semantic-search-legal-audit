# AGENTS.md

**audit-legal** — hệ thống RAG đối chiếu **dự thảo văn bản** với **kho pháp luật Việt Nam**: với từng khoản/điểm của dự thảo, tìm căn cứ pháp lý, cho LLM kết luận `VI_PHAM` / `HOP_LE` / `CHUA_XAC_DINH` kèm trích dẫn và đề xuất sửa (xuất được DOCX track-change). Có thêm hỏi đáp pháp luật (`/ask`). Khóa luận tốt nghiệp; repo private.

Python ≥ 3.10, FastAPI, PostgreSQL 16 + pgvector, psycopg3 (không ORM), **không LangChain/LlamaIndex**. Model gọi qua HTTP: LLM chính **Qwen3:14b qua Ollama** (Gemini là phụ), embedding bge-m3 (1024d), rerank bge-reranker-v2-m3 qua TEI.

## Bản đồ

| Ở đâu | Là gì | Đọc |
|---|---|---|
| `app/core/` | cấu hình, pool DB, client LLM/embedding — dùng chung | [ARCHITECTURE](app/core/ARCHITECTURE.md) |
| `app/crawl/` | service 1: cào vbpl.vn → schema `vanban` | [ARCHITECTURE](app/crawl/ARCHITECTURE.md) · [CONSTRAINTS](app/crawl/CONSTRAINTS.md) |
| `app/doisanh/` | service 2: dựng cây + chunk, truy hồi, audit, hỏi đáp, API + UI | [ARCHITECTURE](app/doisanh/ARCHITECTURE.md) · [audit CONSTRAINTS](app/doisanh/audit/CONSTRAINTS.md) |
| `migrations/` | schema SQL `danhmuc` / `vanban` / `rag` | [ARCHITECTURE](migrations/ARCHITECTURE.md) · [CONSTRAINTS](migrations/CONSTRAINTS.md) |
| `scripts/` | `init_db.py` (áp migration), `embed_chunks.py`; `fetch_*.py` để thăm dò API vbpl; phần còn lại là di sản | — |
| `.claude/skills/` | quy ước chi tiết theo chủ đề (code sạch, parser luật, DB, audit) | đọc khi chạm vùng tương ứng |
| [PROGRESS.md](PROGRESS.md) | đã xong / đang làm / tiếp theo | **đọc trước khi bắt đầu việc** |

## Cách chạy

```bash
python tasks.py setup      # .venv + dependency (Windows không có make; Linux có thể dùng `make setup`)
```

Cần file `.env` ở gốc (không commit, không có mẫu trong repo) — tên biến và mặc định đọc ở `app/core/config.py`. Tối thiểu `DB_URL`; chạy thật cần thêm Ollama (LLM + embedding), tùy chọn `RERANK_URL`.

```bash
python scripts/init_db.py                          # áp migrations (idempotent)
python -m app.crawl.cli crawl-full --id <ID>       # cào 1 văn bản (metadata + cây)
python -m app.crawl.cli fetch-tac-dong             # tác động sửa đổi
python -m app.doisanh.cli build-cay --embed        # dựng node/chunk + embedding
python -m app.doisanh.cli port-impacts             # SAU build-cay
uvicorn app.doisanh.api.main:app --port 8010       # API + UI tại http://localhost:8010
```

Không có `--reload` thì phải khởi động lại uvicorn sau khi sửa code.

## Cách xác minh

```bash
python tasks.py check      # lint (compileall) + pytest offline — phải xanh trước khi commit
python -m pytest tests/audit/test_validate.py -q   # một file; thêm ::ten_test cho một test
```

- Test offline không cần DB/LLM. Test cần thật đánh dấu `@pytest.mark.llm` / `@pytest.mark.integration`, không chạy trong `check`.
- **Chưa có bộ eval cho luồng `/audit` hiện tại** — đổi prompt/retrieval phải kiểm tay trên dự thảo mẫu qua UI hoặc `POST /audit`, và ghi lại ca đã thử.
- Soi retrieval: `python tests/debug_retrieval.py "câu hỏi"` (cần DB + embedding).

## Ràng buộc cứng

- `app/core` không import service nào; `app/crawl` và `app/doisanh` **không import lẫn nhau**, chỉ gặp nhau qua DB.
- Chỉ `app/crawl` được gọi vbpl.vn, tuần tự và có giãn cách.
- DB chỉ qua `ket_noi()`, SQL tham số hóa. **Không sửa migration đã áp dụng** — thêm file số kế tiếp.
- **Luồng audit đang chạy là `api/routes_simple.py` → `audit/so_sanh.py`.** `workflow.py`, `mapping.py`, `tier2.py`… là di sản bám schema đã drop — đừng sửa chúng để thay đổi hành vi `/audit`.
- Không commit `.env`, mật khẩu, DB URL thật, hay các tệp `.gitignore` đang chặn (tài liệu nội bộ chứa thông tin nhạy cảm, cấu hình Docker). Repo đã chủ động gỡ tên tổ chức khỏi code/tài liệu (commit `62a64bc`) — đừng đưa lại.
- Commit dưới tên tác giả repo, **không thêm dòng `Co-Authored-By` của AI**. Định dạng message: `[update]: …`, `[fix]: …`, `chore: …`, tiếng Việt.
- Quy ước tên: code hiện tại dùng tiếng Việt không dấu (`ket_noi`, `tim_hybrid`); đã quyết định **chuyển toàn bộ sang tiếng Anh** (xem PROGRESS.md). Code mới viết tên tiếng Anh; đừng tự đổi tên code cũ ngoài đợt đổi tên.
