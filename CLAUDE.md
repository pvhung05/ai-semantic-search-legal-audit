# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# audit_rag – hướng dẫn cho Claude Code

Dự án: service đối chiếu văn bản dự thảo với kho pháp luật Việt Nam (PostgreSQL + pgvector, FastAPI, LLM qua HTTP OpenAI-compatible). Kế hoạch chi tiết ở `PLAN.md` (v3), phân tích kiến trúc ở `KIEN_TRUC_HE_THONG.md`. **Không dùng LlamaIndex/LangChain** — toàn bộ pipeline là Python thuần + psycopg3.

## Trước mỗi task
1. Đọc `PLAN.md` mục 1 (cách tiếp cận), 4 (schema), 6 (quy ước); tìm task + trạng thái trong mục 7 và 10.
2. Mở skill tương ứng trong `.claude/skills/` (nạp tự động theo mô tả):
   - `clean-code-solid` – chuẩn code, kiến trúc, test: áp dụng cho **mọi** task Python.
   - `legal-db-schema` – khi chạm `migrations/`, `app/db/`, SQL, hiệu lực, phiên bản.
   - `vn-law-parser` – khi chạm `app/ingestion/`, regex văn bản luật, dẫn chiếu, lệnh sửa đổi.
   - `legal-audit-workflow` – khi chạm `app/audit/`, prompt, báo cáo, API audit.

## Lệnh thường dùng
Môi trường: `.venv`, Python 3.10+, `.env` chép từ `.env.example`. DB là Postgres 16 + pgvector (container `pg-luatvn`, cổng 5433, db `luatvn`). Shell chính là PowerShell trên Windows.

```bash
pip install -e ".[dev]"                 # cài gồm pytest
python scripts/init_db.py               # áp dụng migrations/*.sql tuần tự (idempotent qua schema_migrations)
uvicorn app.doisanh.api.main:app --reload --port 8010   # service đối sánh: API + UI tại http://localhost:8010

pytest                                  # toàn bộ test
pytest tests/test_parser.py             # một file
pytest tests/test_parser.py::test_tach_dieu_co_ban   # một test
pytest -m "not llm and not integration" # bỏ qua test cần LLM/DB thật (marker ở pyproject.toml)
```

Test đánh dấu `@pytest.mark.llm` cần `LLM_URL` thật; `@pytest.mark.integration` cần DB thật. Trong test thường, LLM dùng mock trả JSON cố định. Chưa có linter/formatter cấu hình — theo style sẵn có (type hints, `from __future__ import annotations`, pydantic cho mọi dataclass).

Pipeline dữ liệu (xem docstring đầu mỗi CLI/script để biết tham số):
```bash
# Service CRAWL (chỉ ghi meta; nơi DUY NHẤT gọi vbpl.vn)
python -m app.crawl.cli seed-actions|seed-catalogs|discover|crawl|fetch-cay|stats

# Service ĐỐI SÁNH (đọc meta, ghi/đọc public; không gọi mạng)
python -m app.doisanh.cli build-cay --id <ID>        # dựng public.node từ meta.document_cay
python scripts/ingest.py --file <luat.pdf> --id <ID> --loai <loai> ...   # nạp 1 văn bản luật từ file
python scripts/sync.py                                                   # thi hành lệnh sửa đổi + cập nhật trạng thái
python scripts/audit.py --file <du_thao.docx> --loai du_thao_thong_tu --ngay <YYYY-MM-DD> --auto
```

## Kiến trúc tổng thể — hai service dùng chung `app/core`
Repo tách thành **2 service deploy độc lập** + 1 package lõi, chung 1 Postgres (giữ FK `public.van_ban → meta.documents`). Bất biến: `core` không import service nào; **crawl và doisanh không import lẫn nhau**, chỉ import `core`.

- **`app/core/`** (dùng chung): `config.py` (`Settings` pydantic đọc `.env`; **Dual-LLM** `IS_LOCAL=true` Qwen3 local / `false` Gemini, `LLM_URL/MODEL/API_KEY` do `_chon_llm` tự chọn — đừng hardcode; import qua `from app.core.config import settings`); `db/session.ket_noi()` (pool psycopg, cổng DB duy nhất); `models/` (`llm`, `embedder`, `schemas`); `html_text.html_doc_to_text`.
- **`app/crawl/`** (SERVICE 1 → chỉ ghi `meta`; nơi DUY NHẤT gọi vbpl.vn): cào vbpl.vn (Next.js Server Actions; `actions.py` giữ action-id, đổi khi site deploy lại) → `meta.documents`, `document_content`, `document_relations`, danh mục. Lệnh `fetch-cay` lưu cây nội dung thô (JSON) vào `meta.document_cay`. Entrypoint `app/crawl/cli.py` (hoặc wrapper `scripts/crawl_vbpl.py`).
- **`app/doisanh/`** (SERVICE 2 → đọc/ghi `public`, đối sánh; **không gọi mạng**): entrypoint API `app/doisanh/api/main.py` + CLI `app/doisanh/cli.py`.
  - `public_loader.build_cay_tu_meta` đọc `meta.document_cay` → dựng `public.node`/`public.chunk` (cầu nối meta→public, offline). CLI `build-cay`.
  - `db/repo_*.py` gói mọi SQL; `ingestion`/`audit` **không viết SQL riêng**, đi qua `db/`.
  - `ingestion/` – `loader`→`parser`→`pipeline.nap_van_ban`; `amend_parser`, `citation_parser`, `summarize`, `sync`, `chunks`.
  - `audit/` – `segment`, `parent_docs`, `consolidate`, `tier1`, `mapping`, `tier2`, `focus_khoan` (hybrid BM25+embedding chọn Khoản mẹ), `fallback`, `workflow` (lưu `buoc`, dừng/duyệt/tiếp tục, song song theo `LLM_SONG_SONG`), `prompts`, `report`.
  - `retrieval/hybrid.py`, `qa/chat.py`, `api/routes_simple.py` (4 endpoint: `POST /ask`, `/upload/legal`, `/upload/draft`, `/audit`; UI ở `api/static/index.html`).

Luồng đối sánh cốt lõi (chi tiết `PLAN.md` mục 1): upload dự thảo → **segment** → **parent_docs** (duyệt) → **tier1** (không LLM) → **mapping** (LLM, duyệt) → **tier2** (LLM, chỉ kết luận khi trích được nguyên văn căn cứ) → báo cáo.

### Schema DB — chú ý sự phân kỳ với PLAN.md
`init_db.py` chạy **tất cả** `migrations/*.sql` theo thứ tự tên:
- `001_init.sql` – schema v3 cũ (`dieu_luat`/`khoan`/`quan_he_van_ban` + 5 hàm hiệu lực). **Đã bị 003 drop phần lớn.**
- `002_meta_vbpl.sql` – schema `meta`: metadata crawl từ vbpl.vn (`documents`, danh mục, lược đồ quan hệ).
- `003_public_cay.sql` – **model hiện hành**: pivot kho luật sang CÂY. Một bảng `node` thống nhất (adjacency list) cho Phần/Chương/Mục/Điều/Khoản/Điểm, **khóa = UUID vbpl** (không ghép id thủ công). `van_ban.id` = id vbpl, FK sang `meta.documents`. Quan hệ sửa đổi cấp điều khoản ở `tac_dong` (`node_dich_id ← node_nguon_id`). View `v_dieu`/`v_khoan` đọc theo cấp.
- `004_cap_node_phan.sql` – thêm cấp `phan` (Part) vào enum.
- `005_meta_cay.sql` – bảng `meta.document_cay` chứa cây nội dung thô (JSON) do service crawl ghi; service đối sánh đọc để dựng `public.node`.

PLAN.md mục 4b và nhiều mô tả `app/ingestion`/`app/audit` vẫn bám `dieu_luat`/`khoan` cũ — đang **chờ viết lại** trên `node`/`tac_dong`. Khi chạm DB, xác minh bảng/hàm thực tế trong migration mới nhất trước, đừng tin mô tả schema cũ.

## Luật bất di bất dịch
- Không bịa nội dung luật, không tự chế văn bản để test. Thiếu dữ liệu thật → **dừng và hỏi**.
- Không sửa migration đã áp dụng; không đổi tên bảng/cột. Migration mới = file số thứ tự tiếp theo.
- Mọi phát hiện đối chiếu phải có căn cứ là bản ghi thật trong DB (`node.id`/`khoan.id`); LLM không được bịa căn cứ (id phải thuộc tập đưa vào prompt, trích dẫn khớp nguyên văn fuzz ≥ 85).
- Mỗi task một commit `GĐ<X><n> <module>: <việc>`; test đi cùng code; cập nhật `PLAN.md` mục 10.
