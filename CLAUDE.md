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
python -m app.crawl.cli crawl-full --id <ID> [<ID> ...]   # crawl metadata + fetch-cay trong 1 lệnh (nhiều ID)

# Service ĐỐI SÁNH (đọc meta, ghi/đọc public; không gọi mạng)
python -m app.doisanh.cli build-cay --id <ID> --embed  # dựng public.node/chunk + sinh embedding luôn

# Luồng test end-to-end (sau khi đã có kho luật bằng 2 lệnh trên):
#   curl -F file=@du_thao.docx http://localhost:8010/upload/draft      # -> tai_lieu_id
#   curl -X POST http://localhost:8010/audit -H 'Content-Type: application/json' \
#        -d '{"tai_lieu_id":"TL-xxxx","top_k":5}'                      # -> VI_PHAM/HOP_LE/CHUA_XAC_DINH
python scripts/ingest.py --file <luat.pdf> --id <ID> --loai <loai> ...   # nạp 1 văn bản luật từ file
python scripts/sync.py                                                   # thi hành lệnh sửa đổi + cập nhật trạng thái
python scripts/audit.py --file <du_thao.docx> --loai du_thao_thong_tu --ngay <YYYY-MM-DD> --auto
```

## Kiến trúc tổng thể — hai service dùng chung `app/core`
Repo tách thành **2 service deploy độc lập** + 1 package lõi, chung 1 Postgres (giữ FK `public.van_ban → meta.documents`). Bất biến: `core` không import service nào; **crawl và doisanh không import lẫn nhau**, chỉ import `core`.

- **`app/core/`** (dùng chung): `config.py` (`Settings` pydantic đọc `.env`; **Dual-LLM** `IS_LOCAL=true` Qwen3 local / `false` Claude (Anthropic OpenAI-compat), `LLM_URL/MODEL/API_KEY` do `_chon_llm` tự chọn — đừng hardcode; import qua `from app.core.config import settings`); `db/session.ket_noi()` (pool psycopg, cổng DB duy nhất); `models/` (`llm`, `embedder`, `schemas`); `html_text.html_doc_to_text`.
- **`app/crawl/`** (SERVICE 1 → chỉ ghi `meta`; nơi DUY NHẤT gọi vbpl.vn): cào vbpl.vn (Next.js Server Actions; `actions.py` giữ action-id, đổi khi site deploy lại) → `meta.documents`, `document_content`, `document_relations`, danh mục. Lệnh `fetch-cay` lưu cây nội dung thô (JSON) vào `meta.document_cay`. Entrypoint `app/crawl/cli.py` (hoặc wrapper `scripts/crawl_vbpl.py`).
- **`app/doisanh/`** (SERVICE 2 → đọc/ghi `public`, đối sánh; **không gọi mạng**): entrypoint API `app/doisanh/api/main.py` + CLI `app/doisanh/cli.py`.
  - `public_loader.build_cay_tu_meta` đọc `meta.document_cay` → dựng `public.node`/`public.chunk` (cầu nối meta→public, offline). CLI `build-cay`.
  - `db/repo_*.py` gói mọi SQL; `ingestion`/`audit` **không viết SQL riêng**, đi qua `db/`.
  - `ingestion/` – `loader`→`parser`→`pipeline.nap_van_ban`; `amend_parser`, `citation_parser`, `summarize`, `sync`, `chunks`.
  - `audit/` – `segment`, `parent_docs`, `consolidate`, `tier1`, `mapping`, `tier2`, `focus_khoan` (hybrid BM25+embedding chọn Khoản mẹ), `fallback`, `workflow` (lưu `buoc`, dừng/duyệt/tiếp tục, song song theo `LLM_SONG_SONG`), `prompts`, `report`.
  - `retrieval/hybrid.py`, `qa/chat.py`, `api/routes_simple.py` (4 endpoint: `POST /ask`, `/upload/legal`, `/upload/draft`, `/audit`; UI ở `api/static/index.html`).

Luồng đối sánh cốt lõi (chi tiết `PLAN.md` mục 1): upload dự thảo → **segment** → **parent_docs** (duyệt) → **tier1** (không LLM) → **mapping** (LLM, duyệt) → **tier2** (LLM, chỉ kết luận khi trích được nguyên văn căn cứ) → báo cáo.

Có **hai đường chạy audit, đừng lẫn**:
- **Workflow có trạng thái** (`audit/workflow.py`, `scripts/audit.py`, `db/repo_audit.py`): máy trạng thái lưu ở cột `phien.buoc` — `tao → cho_duyet_vb_me → tier1 → (cho_duyet_anh_xa) → tier2 → fallback → xong` (hoặc `loi`). `tao_phien_tu_du_thao()` tạo phiên; `tiep_tuc(phien_id)` chạy tới bước chờ-duyệt/xong kế tiếp; `duyet_vb_me`/`duyet_anh_xa` mở khoá bước duyệt; `tu_dong_duyet=True` bỏ qua duyệt. Flow hiện hành **bỏ mapping LLM** (tier1 → thẳng tier2, focus cấp Khoản bằng embedding ở `focus_khoan`), và `fallback` đang no-op (bật lại qua `ENABLE_FALLBACK`).
- **Endpoint stateless** `POST /audit` (`api/routes_simple.py`): không phiên, không duyệt — đọc đơn vị từ `du_thao_node` (dùng lại `embedding` đã sinh lúc upload) → hybrid toàn kho (hoặc trong `van_ban_me_ids` nếu truyền) → LLM tier2 so sánh → gom `VI_PHAM`/`HOP_LE`/`CHUA_XAC_DINH`. `_nap_khoan_ung_vien` gom ứng viên từ `chunk → node` và tách định danh Điều/Khoản/Điểm bằng `public_loader.tach_duong_dan(node.duong_dan)`; `text_embed` của chunk đã đủ ngữ cảnh nên dùng trực tiếp. Tier1 (dẫn chiếu/hiệu lực) gated off tới khi port.

Cả hai chạy song song theo `settings.LLM_SONG_SONG` (ThreadPoolExecutor) — **mỗi thread mở `ket_noi()` riêng**, không chia sẻ connection. LLM gọi qua `goi_json`/`goi_chat`, tham số `is_local` truyền xuyên suốt từ request (None=theo `.env`).

### Schema DB — chú ý sự phân kỳ với PLAN.md
`init_db.py` chạy **tất cả** `migrations/*.sql` theo thứ tự tên:
- `001_init.sql` – schema v3 cũ (`dieu_luat`/`khoan`/`quan_he_van_ban` + 5 hàm hiệu lực). **Đã bị 003 drop phần lớn.**
- `002_meta_vbpl.sql` – schema `meta`: metadata crawl từ vbpl.vn (`documents`, danh mục, lược đồ quan hệ).
- `003_public_cay.sql` – **model hiện hành**: pivot kho luật sang CÂY. Một bảng `node` thống nhất (adjacency list) cho Phần/Chương/Mục/Điều/Khoản/Điểm, **khóa = UUID vbpl** (không ghép id thủ công). `van_ban.id` = id vbpl, FK sang `meta.documents`. Quan hệ sửa đổi cấp điều khoản ở `tac_dong` (`node_dich_id ← node_nguon_id`). View `v_dieu`/`v_khoan` đọc theo cấp.
- `004_cap_node_phan.sql` – thêm cấp `phan` (Part) vào enum.
- `005_meta_cay.sql` – bảng `meta.document_cay` chứa cây nội dung thô (JSON) do service crawl ghi; service đối sánh đọc để dựng `public.node`.
- `006_view_node_chunk.sql` – view `v_node_chunk` (node + chunk cạnh nhau: cap, tiêu đề, text_goc/text_embed) để soi dữ liệu.
- `007_ham_tim_kiem_hybrid.sql` – **dựng lại** `tim_kiem_hybrid()` cho `public.chunk` (node_id): vector cosine + BM25, hợp nhất RRF. 003 đã drop hàm này. Tham số `p_cap_max`/`p_linh_vuc` giữ cho tương thích nhưng KHÔNG áp dụng.
- `008_du_thao_cay.sql` – kho **dự thảo**, đối xứng `van_ban → node/chunk`: `du_thao` (`id, noi_dung, cay jsonb, created_at` — user chỉ upload file, không nhập metadata; `cay` = KetQuaSegment JSON gốc) + `du_thao_node` (kho chunk: mỗi đơn vị 1 dòng, có `text_embed` + `embedding vector(1024)`). Thay 2 bảng `tai_lieu`/`tai_lieu_don_vi` cũ (đã bị 003 drop). `cap` dùng `text` vì segment dự thảo còn cấp `doan`/`cum`.

Luồng end-to-end đối sánh (đã chạy được trên node/chunk): `crawl-full` → `build-cay --embed` (dựng kho luật + embedding) → `POST /upload/draft` (segment → `du_thao` + `du_thao_node` + embedding) → `POST /audit` (mỗi đơn vị dùng lại vector đã lưu → hybrid toàn kho/VB mẹ → LLM tier2 → VI_PHAM/HOP_LE/CHUA_XAC_DINH). `/ask` cũng đã port sang node/chunk.

**Còn bám schema cũ (chưa port, KHÔNG dùng trong luồng test):** `tier1` + `repo_hieu_luc` + `consolidate` (cần `dieu_luat`/`khoan` + 5 hàm hiệu lực đã bị 003 drop). `tier1` trong `/audit` đang **tắt** theo `settings.ENABLE_TIER1` (mặc định False). Workflow có trạng thái (`audit/workflow.py`, `scripts/audit.py`) và `/upload/legal` (ingestion từ file) cũng chưa port. Khi chạm DB, xác minh bảng/hàm thực tế trong migration mới nhất trước, đừng tin mô tả schema cũ.

## Luật bất di bất dịch
- Không bịa nội dung luật, không tự chế văn bản để test. Thiếu dữ liệu thật → **dừng và hỏi**.
- Không sửa migration đã áp dụng; không đổi tên bảng/cột. Migration mới = file số thứ tự tiếp theo.
- Mọi phát hiện đối chiếu phải có căn cứ là bản ghi thật trong DB (`node.id`/`khoan.id`); LLM không được bịa căn cứ (id phải thuộc tập đưa vào prompt, trích dẫn khớp nguyên văn fuzz ≥ 85).
- Mỗi task một commit `GĐ<X><n> <module>: <việc>`; test đi cùng code; cập nhật `PLAN.md` mục 10.
