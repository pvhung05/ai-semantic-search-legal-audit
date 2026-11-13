# app/core — lõi dùng chung

**Trách nhiệm:** cấu hình, kết nối DB, client gọi model (LLM, embedding), pydantic model dùng chung, chuyển HTML vbpl → text. Không chứa nghiệp vụ.

**Giao diện với module khác**
- Cả `app/crawl` và `app/doisanh` import từ đây; `core` **không import ngược** service nào.
- `config.settings` (singleton) — nguồn duy nhất của biến môi trường. Danh sách biến và giá trị mặc định: đọc thẳng [config.py](config.py) (repo không commit `.env.example`).
- `db.session.ket_noi()` — cổng DB duy nhất (pool psycopg, `autocommit=False`, mỗi thread tự mở kết nối). Caller tự `commit()`.
- `models.llm.goi_chat` / `goi_json` — mọi lời gọi LLM đi qua đây. Mỗi lời gọi HTTP tự retry có backoff (tenacity); `goi_json` cắt rào ``` và gọi lại thêm 1 lần khi parse JSON lỗi (nên một đơn vị có thể tốn tới vài lời gọi LLM), lỗi cuối ném `LoiLLM`/`LoiParseJSON`.
- `models.embedder.embed` / `embed_batch` — embedding bge-m3, 1024 chiều (`EMBED_DIM` phải khớp cột `vector(1024)` trong DB).

**Quyết định thiết kế**
- **Hai đường LLM, chọn theo `is_local`** (`Settings.cau_hinh_llm`). Mỗi request API có thể ghi đè `is_local` và `think`.
  - `is_local=True` (**mặc định, Qwen3:14b qua Ollama — model chính của dự án**): gọi endpoint *native* `/api/chat`, không phải `/v1`, vì chỉ native mới tắt được thinking thật (`think:false`) và nhận `options.num_ctx`.
  - `is_local=False`: Gemini qua endpoint OpenAI-compatible `/chat/completions`. (Comment trong `config.py`, `models/llm.py` và mô tả field `is_local` trong `routes_simple.py` còn ghi "Claude" — đã lỗi thời.)
- Không ORM, không framework RAG: SQL tay qua psycopg3, model gọi qua HTTP (httpx + tenacity). Lý do chọn: TODO: cần xác nhận.
- `Settings()` khởi tạo ngay khi import và **bắt buộc có `DB_URL`** — thiếu thì mọi import `app.core.config` đều lỗi, kể cả khi chạy test offline (`tasks.py test` tự đặt giá trị giả nếu thiếu).
