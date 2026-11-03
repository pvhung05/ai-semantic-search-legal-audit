# LEGAL AUDIT – Kế hoạch v3: service đối chiếu văn bản dự thảo với kho pháp luật

> Tài liệu điều phối cho Claude Code. **v3 thay thế toàn bộ v2 và PLAN_DOI_CHIEU.** Đọc hết trước khi làm bất cứ task nào.
> Cơ sở dữ liệu được **tạo lại từ đầu** (xóa DB cũ). Code GĐ1–3 cũ được giữ lại những phần còn dùng (loader, normalize, parser, embedder, llm, config) và sắp xếp lại theo cấu trúc mới.
> Làm theo đúng thứ tự task; mỗi task có tiêu chí hoàn thành.

---

## 0. Mục tiêu và phạm vi

### Sản phẩm demo

Một chương trình chạy local, thao tác qua web UI đơn giản (hoặc CLI), gồm ba bước:

1. **Upload luật**: tải lên file luật/nghị định/thông tư (docx/pdf/txt), kể cả văn bản sửa đổi. Hệ thống parse thành Điều/Khoản, nhận diện lệnh sửa đổi, tính hiệu lực.
2. **Upload dự thảo**: tải lên dự thảo (thông tư, nghị định, quy chế nội bộ...), chọn ngày dự kiến ban hành.
3. **Đối chiếu**: trả về danh sách **điểm sai trong dự thảo**, mỗi điểm gồm: vị trí (Điều/Khoản dự thảo), loại sai, mức độ, **căn cứ pháp lý** (văn bản, Điều, Khoản, trích nguyên văn), giải thích, đề xuất sửa. Người dùng duyệt danh sách văn bản mẹ và bảng ánh xạ trước khi chạy so sánh.

### Loại sai phải phát hiện được trong demo

| Nhóm | loai_loi | Cách phát hiện | LLM |
|---|---|---|---|
| Dẫn chiếu | `dan_chieu_khong_ton_tai`, `dan_chieu_sai_so_hieu` | regex + tra bảng | không |
| Hiệu lực | `dan_het_hieu_luc`, `dan_bi_bai_bo`, `dan_chua_hieu_luc` | đồ thị sửa đổi + hàm tra theo ngày | không |
| Nguyên văn | `trich_sai_nguyen_van` | diff chuỗi với khoản gốc | không |
| Thể thức | `the_thuc` | rule | không |
| Nội dung | `thu_hep_pham_vi`, `mo_rong_pham_vi`, `them_dieu_kien`, `them_nghia_vu`, `doi_so_lieu`, `dat_thu_tuc_moi`, `mau_thuan_truc_tiep`, `vuot_tham_quyen` | ánh xạ Điều ↔ Điều mẹ, so sánh nguyên văn hai bên | có |
| Thiếu căn cứ | `khong_co_can_cu_uy_quyen` | Điều không ánh xạ được | có |

### Ngoài phạm vi demo (để sau)

Crawl vbpl.vn, đa người dùng/RLS, chatbot hỏi đáp, reranker. Schema đã chừa chỗ.

---

## 1. Cách tiếp cận

Dự thảo không thể trái với "toàn bộ kho"; nó chỉ có thể trái với một **tập văn bản mẹ** xác định được trước (phần Căn cứ + đồ thị quan hệ, thường 3–6 văn bản). Vì vậy:

```
upload dự thảo
  └─► segment: tách Điều/Khoản (hoặc đề mục/đoạn/cụm nếu không có Điều) + trích Căn cứ + dẫn chiếu
       └─► parent_docs: xác định văn bản mẹ, lấy bản hợp nhất tại ngày dự kiến     [người dùng duyệt]
            └─► tier1: dẫn chiếu, hiệu lực, nguyên văn, thể thức (không LLM, chạy toàn bộ)
                 └─► mapping: LLM đọc mục lục hai bên → Điều dự thảo ↔ Điều mẹ      [người dùng duyệt]
                      ├─► tier2: mỗi cặp → LLM đọc nguyên văn hai bên → phát hiện có căn cứ
                      └─► fallback: Điều mồ côi → truy hồi hybrid (GĐ E) → tier2, hoặc "không có căn cứ ủy quyền"
                           └─► ket_qua_doi_chieu → báo cáo / UI
```

Ba tầng dưới (kho có cấu trúc, hàm tra hiệu lực, retriever) không biết gì về "dự thảo"; `audit/` là client của chúng. Truy hồi bằng embedding là **đường dự phòng**; demo chạy được không cần nó.

### Nguyên tắc

1. `van_ban`, `dieu_luat`, `khoan`, `quan_he_van_ban`, `dan_chieu` là nguồn sự thật; `chunk` là dẫn xuất.
2. Lưu **sự kiện** (lệnh sửa đổi) rồi tính trạng thái; không nhập tay trạng thái.
3. **Phiên bản theo thời gian**: không ghi đè Điều/Khoản bị sửa; mọi tra cứu theo ngày.
4. Hai tầng kiểm tra: xác định trước, LLM sau và chỉ cho phần cần.
5. Mọi phát hiện phải có căn cứ trỏ về `khoan.id`/`dieu_luat.id` thật trong DB; LLM không được bịa căn cứ (kiểm tra id thuộc tập đã đưa vào prompt, trích dẫn khớp nguyên văn).
6. Cấu hình qua `.env` (`app/config.py`); model gọi HTTP OpenAI-compatible; không hardcode.
7. Không bịa nội dung luật. Cần văn bản thật → dừng và hỏi.

---

## 2. Môi trường và khởi tạo lại DB

- Postgres 16 + pgvector, container `pg-luatvn`, cổng 5433, user `audit_rag`, db `luatvn`.
- Ollama: `qwen3:14b` (hoặc lớn hơn cho tier2); `bge-m3` chỉ cần ở GĐ E.
- Python 3.10+, `.venv`.

Xóa và tạo lại (bỏ hoàn toàn dữ liệu cũ):

```bash
docker rm -f pg-luatvn
docker volume rm pg_luatvn_data
docker run -d --name pg-luatvn --restart unless-stopped -e POSTGRES_USER=audit_rag -e POSTGRES_PASSWORD=REDACTED -e POSTGRES_DB=luatvn -p 5433:5432 -v pg_luatvn_data:/var/lib/postgresql/data pgvector/pgvector:pg16
python scripts/init_db.py          # áp dụng migrations/001_init.sql
```

Xóa thư mục `migrations/` cũ; v3 bắt đầu lại từ `001_init.sql`.

---

## 3. Cấu trúc project

> **v3.2 — `app/` đã tách thành 2 service + lõi dùng chung** (xem mục 10, dòng V3.2-split):
> `app/core/` (config, db/session, models, html_text) · `app/crawl/` (ghi `meta`) · `app/doisanh/`
> (ghi/đọc `public`, đối sánh). Cây dưới đây là bố cục gốc một-service, giữ làm tham chiếu lịch sử.

```
audit_rag/
  .env  .env.example  pyproject.toml  README.md  PLAN.md
  migrations/
    001_init.sql                 # toàn bộ schema v3 (mục 4)
  app/
    config.py
    db/
      session.py                 # pool psycopg
      repo_van_ban.py            # upsert van_ban/dieu_luat/khoan, get_muc_luc, get_dieu_full
      repo_hieu_luc.py           # khoan_hieu_luc_tai, ban_hop_nhat, apply_lenh, tinh_trang_thai
      repo_tai_lieu.py           # tai_lieu, don_vi, dan_chieu
      repo_audit.py              # phien, van_ban_me, anh_xa, ket_qua, cache
    models/
      embedder.py  llm.py        # giữ từ v2
      schemas.py                 # pydantic: VanBanMeta, Dieu, Khoan, LenhSuaDoi, DanChieu, DonVi, AnhXa, PhatHien
    ingestion/
      loader.py  normalize.py  parser.py        # giữ từ v2, sửa so_dieu → str
      amend_parser.py            # văn bản sửa đổi → list[LenhSuaDoi]
      citation_parser.py         # text → list[DanChieu]
      summarize.py               # tóm tắt 1 câu cho mỗi Điều (LLM, batch)
      pipeline.py                # nap_van_ban(file, meta) → DB (+ lệnh sửa đổi nếu là VB sửa đổi)
      sync.py                    # thi hành lệnh chưa áp dụng, tính trạng thái
      chunks.py                  # (GĐ E) tạo chunk + embedding
    audit/
      segment.py  parent_docs.py  consolidate.py  tier1.py  mapping.py  tier2.py  fallback.py
      workflow.py  prompts.py  report.py
    retrieval/
      hybrid.py                  # (GĐ E)
    api/
      main.py  schemas.py
      routes_van_ban.py  routes_tai_lieu.py  routes_audit.py
      static/index.html          # UI demo một trang (HTML + JS thuần)
  scripts/
    init_db.py  ingest.py  sync.py  audit.py  eval_audit.py  seed_demo.py
  tests/
    data/  test_normalize.py  test_parser.py  test_amend_parser.py  test_citation_parser.py
    audit/  test_segment.py  test_parent_docs.py  test_tier1.py  test_mapping.py  test_tier2.py
  data/raw/  data/private/      # gitignore
```

---

## 4. Schema (`migrations/003_public_cay.sql`)

> **v3.1 — kho pháp luật chuyển sang model CÂY lấy từ API vbpl.vn.**
> `public` được dựng lại từ `003_public_cay.sql`: **một bảng `node` thống nhất** (adjacency
> list) cho Chương/Mục/Điều/Khoản/Điểm, **khóa = UUID của vbpl** (bỏ id ghép `VB:D5:K2`).
> `van_ban.id` = **id vbpl trực tiếp** và dùng lại metadata đã crawl ở schema `meta`
> (`meta.documents`). Liên kết sửa đổi ở **cấp điều khoản** nằm ở `tac_dong`
> (`node_dich_id ← node_nguon_id`, xuyên văn bản).
>
> Các bảng tài liệu/đối chiếu/eval và 5 hàm hiệu lực của v3 cũ (`khoan_hieu_luc_tai`,
> `ban_hop_nhat`, `van_ban_me_qua_do_thi`…) **đã gỡ** — phần dưới (§4b) giữ nguyên spec cũ
> làm tham chiếu, **chờ thiết kế lại** bám theo `node`/`tac_dong`. app/ingestion + app/audit
> hiện trỏ vào bảng cũ nên sẽ viết lại ở giai đoạn sau.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE cap_node       AS ENUM ('phan','chuong','muc','dieu','khoan','diem'); -- 'phan' them o migration 004
CREATE TYPE trangthai_node AS ENUM
  ('chua_hieu_luc','con_hieu_luc','het_hieu_luc_mot_phan','het_hieu_luc','bai_bo','khong_xac_dinh');
CREATE TYPE loai_tacdong   AS ENUM
  ('sua_doi','bo_sung','bai_bo','thay_the','dinh_chi','huong_dan','thay_cum_tu');

-- ====================== KHO PHÁP LUẬT — MODEL CÂY (nguồn: API vbpl) ======================
-- Văn bản: dùng lại metadata đã crawl ở meta.documents (không lặp lại)
CREATE TABLE van_ban (
  id                text PRIMARY KEY REFERENCES meta.documents(id) ON DELETE CASCADE,  -- = vbpl id
  so_hieu text, ten text, loai text,
  ngay_ban_hanh date, ngay_hieu_luc date, ngay_het_hieu_luc date,
  trang_thai        trangthai_node NOT NULL DEFAULT 'khong_xac_dinh',
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- CÂY nội dung: 1 dòng = 1 node (Chương/Mục/Điều/Khoản/Điểm) = đơn vị chunk. Khóa = UUID vbpl.
CREATE TABLE node (
  id           text PRIMARY KEY,                               -- UUID node từ API (key/id)
  van_ban_id   text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  parent_id    text REFERENCES node(id) ON DELETE CASCADE,     -- cây cha-con (adjacency list)
  cap          cap_node NOT NULL,                              -- level: Chapter→chuong … Point→diem
  ptype        smallint,                                       -- mã cấp gốc vbpl
  so_thu_tu    text,                                           -- '5','2','a' (parse từ title)
  tieu_de      text, noi_dung text,                            -- title ; content.content (HTML, node lá)
  order_index  int, is_leaf boolean NOT NULL DEFAULT false,
  duong_dan    text,                                           -- 'D5>K2>Da'
  hieu_luc_tu  date, hieu_luc_den date,                        -- effFrom / effTo
  trang_thai   trangthai_node NOT NULL DEFAULT 'khong_xac_dinh',
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX node_vb ON node (van_ban_id, order_index);
CREATE INDEX node_parent ON node (parent_id);
CREATE INDEX node_tra ON node (van_ban_id, cap, so_thu_tu);

-- TÁC ĐỘNG cấp điều khoản: node bị sửa ← node đi sửa (xuyên văn bản), giữ lịch sử
CREATE TABLE tac_dong (
  id               bigserial PRIMARY KEY,
  node_dich_id     text NOT NULL REFERENCES node(id) ON DELETE CASCADE,   -- Điều/Khoản BỊ tác động
  node_nguon_id    text REFERENCES node(id) ON DELETE SET NULL,           -- Điều/Khoản ĐI tác động (lệnh)
  van_ban_nguon_id text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  loai             loai_tacdong NOT NULL,
  ngay_hieu_luc date, cum_tu_cu text, cum_tu_moi text, noi_dung_moi text,
  nguon_lenh       text,                                                  -- nguyên văn lệnh từ luật sửa
  tin_cay          text NOT NULL DEFAULT 'can_ra_soat',                   -- xac_nhan | can_ra_soat
  da_ap_dung       boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tacdong_dich ON tac_dong (node_dich_id, loai);
CREATE INDEX tacdong_nguon ON tac_dong (node_nguon_id);
CREATE INDEX tacdong_vbnguon ON tac_dong (van_ban_nguon_id);

-- CHUNK dẫn xuất cho RAG (tách node dài thành nhiều mẩu khi cần)
CREATE TABLE chunk (
  id           bigserial PRIMARY KEY,
  node_id      text NOT NULL REFERENCES node(id) ON DELETE CASCADE,
  van_ban_id   text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  thu_tu       int NOT NULL DEFAULT 0,
  text_goc     text NOT NULL, text_embed text, embedding vector(1024),
  tsv_goc      tsvector GENERATED ALWAYS AS (to_tsvector('simple', text_goc)) STORED,
  hieu_luc_tu date, hieu_luc_den date, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chunk_node ON chunk (node_id);
CREATE INDEX chunk_vb ON chunk (van_ban_id, hieu_luc_den);
CREATE INDEX chunk_tsv ON chunk USING gin (tsv_goc);

-- View đọc theo cấp (không mất lợi ích 1 bảng)
CREATE VIEW v_dieu  AS SELECT id, van_ban_id, parent_id, so_thu_tu AS so_dieu,  tieu_de, noi_dung,
       order_index, hieu_luc_tu, hieu_luc_den, trang_thai FROM node WHERE cap = 'dieu';
CREATE VIEW v_khoan AS SELECT id, van_ban_id, parent_id, so_thu_tu AS so_khoan, tieu_de, noi_dung,
       order_index, hieu_luc_tu, hieu_luc_den, trang_thai FROM node WHERE cap IN ('khoan','diem');
```

### 4b. Schema v3 cũ — CHỜ THIẾT KẾ LẠI theo `node`/`tac_dong`

> Phần dưới là spec gốc của v3 (tài liệu người dùng, đối chiếu, eval, hàm hiệu lực). Đã gỡ khỏi
> DB ở migration 003 vì FK trỏ `dieu_luat`/`khoan` cũ. Giữ lại để tham chiếu khi dựng lại: mọi
> chỗ `dieu_luat.id`/`khoan.id` sẽ thay bằng `node.id`; hàm tra hiệu lực viết lại trên `node`.

```sql
-- ====================== KHO PHÁP LUẬT v3 CŨ (tham chiếu) ======================
CREATE TABLE van_ban (
  id               text PRIMARY KEY,            -- 'BLLD-2019-45'
  so_hieu          text NOT NULL UNIQUE,        -- '45/2019/QH14'
  ten              text NOT NULL,
  loai             text NOT NULL,               -- hien_phap|bo_luat|luat|nghi_quyet|nghi_dinh|quyet_dinh|thong_tu|khac
  cap              int  NOT NULL,               -- 1 HP, 2 luật/bộ luật, 3 NQ QH, 5 NĐ, 6 QĐ TTg, 7 TT, 8 địa phương
  co_quan_ban_hanh text,
  ngay_ban_hanh    date,
  ngay_hieu_luc    date,
  ngay_het_hieu_luc date,
  ly_do_het        text,                        -- thay_the|bai_bo|het_thoi_han|van_ban_me_het
  trang_thai       text NOT NULL DEFAULT 'con_hieu_luc'
     CHECK (trang_thai IN ('chua_hieu_luc','con_hieu_luc','het_hieu_luc_mot_phan','het_hieu_luc')),
  la_van_ban_sua_doi boolean NOT NULL DEFAULT false,
  linh_vuc         text[] NOT NULL DEFAULT '{}',
  tin_cay          text NOT NULL DEFAULT 'can_ra_soat',   -- xac_nhan|can_ra_soat
  nguon_file       text,
  created_at       timestamptz DEFAULT now()
);

CREATE TABLE dieu_luat (
  id               text PRIMARY KEY,            -- 'BLLD-2019-45:D13' | '...:D13@2026-03-01'
  van_ban_id       text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  so_dieu          text NOT NULL,               -- '13', '54a'
  so_dieu_num      int  NOT NULL,               -- phần số, để sắp xếp
  chuong_so text, chuong_ten text, muc_so text, muc_ten text,
  tieu_de          text,
  noi_dung         text NOT NULL,               -- toàn văn Điều
  tom_tat          text,                        -- 1 câu, sinh bằng LLM
  thu_tu           int  NOT NULL,
  trang_thai       text NOT NULL DEFAULT 'con_hieu_luc',  -- con_hieu_luc|het_hieu_luc|bai_bo|chua_hieu_luc
  hieu_luc_tu      date,
  hieu_luc_den     date,
  thay_boi_id      text REFERENCES dieu_luat(id),
  nguon_sua_doi_id text REFERENCES van_ban(id),
  tin_cay          text NOT NULL DEFAULT 'can_ra_soat'
);
CREATE UNIQUE INDEX dieu_luat_vb_so_tu ON dieu_luat (van_ban_id, so_dieu, COALESCE(hieu_luc_tu, '1900-01-01'));
CREATE INDEX dieu_luat_vb_thutu ON dieu_luat (van_ban_id, thu_tu);

CREATE TABLE khoan (
  id               text PRIMARY KEY,            -- 'X:D13:K2' | 'X:D13:K2:Db' | '...@2026-03-01'
  dieu_id          text NOT NULL REFERENCES dieu_luat(id) ON DELETE CASCADE,
  van_ban_id       text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  so_khoan         text NOT NULL,
  diem             text,                        -- NULL = Khoản
  parent_id        text REFERENCES khoan(id),
  noi_dung         text NOT NULL,
  thu_tu           int  NOT NULL,
  trang_thai       text NOT NULL DEFAULT 'con_hieu_luc',
  hieu_luc_tu      date,
  hieu_luc_den     date,
  thay_boi_id      text REFERENCES khoan(id),
  nguon_sua_doi_id text REFERENCES van_ban(id),
  tin_cay          text NOT NULL DEFAULT 'can_ra_soat'
);
CREATE INDEX khoan_dieu ON khoan (dieu_id, thu_tu);
CREATE INDEX khoan_tra ON khoan (van_ban_id, so_khoan, diem, hieu_luc_den);

CREATE TABLE quan_he_van_ban (
  id             serial PRIMARY KEY,
  nguon_id       text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  dich_id        text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  loai           text NOT NULL CHECK (loai IN
     ('sua_doi','bo_sung','thay_the','bai_bo','huong_dan','quy_dinh_chi_tiet','can_cu','thay_cum_tu')),
  dich_dieu_id   text REFERENCES dieu_luat(id),
  dich_khoan_id  text REFERENCES khoan(id),
  dich_so_dieu   text, dich_so_khoan text, dich_diem text,   -- dạng thô khi chưa phân giải được id
  vi_tri         text,                           -- 'sau'|'truoc' cho bo_sung
  ngay_hieu_luc  date,
  noi_dung_moi   text,
  cum_tu_cu text, cum_tu_moi text,
  nguon_lenh     text,                           -- 'D1:K3'
  tin_cay        text NOT NULL DEFAULT 'can_ra_soat',
  da_ap_dung     boolean NOT NULL DEFAULT false,
  loi_ap_dung    text,
  created_at     timestamptz DEFAULT now()
);
CREATE INDEX quan_he_dich ON quan_he_van_ban (dich_id, loai, da_ap_dung);
CREATE INDEX quan_he_nguon ON quan_he_van_ban (nguon_id);

CREATE TABLE dan_chieu (
  id              serial PRIMARY KEY,
  nguon           text NOT NULL,                 -- luat|tai_lieu
  nguon_khoan_id  text REFERENCES khoan(id) ON DELETE CASCADE,
  nguon_don_vi_id text,                          -- FK tới tai_lieu_don_vi (thêm bên dưới)
  text_dan        text NOT NULL,
  so_hieu text, ten_van_ban text, so_dieu text, so_khoan text, diem text,
  van_ban_id      text REFERENCES van_ban(id),
  dieu_id         text REFERENCES dieu_luat(id),
  khoan_id        text REFERENCES khoan(id),
  ket_qua         text,                          -- hop_le|khong_ton_tai|het_hieu_luc|bai_bo|chua_hieu_luc|sai_so_hieu|khong_xac_dinh
  ngay_tra        date
);
CREATE INDEX dan_chieu_khoan ON dan_chieu (nguon_khoan_id);
CREATE INDEX dan_chieu_don_vi ON dan_chieu (nguon_don_vi_id);

-- ====================== DẪN XUẤT (GĐ E, truy hồi dự phòng) ======================
CREATE TABLE chunk (
  id           text PRIMARY KEY,                 -- = khoan.id hoặc dieu_luat.id
  dieu_id      text NOT NULL REFERENCES dieu_luat(id) ON DELETE CASCADE,
  khoan_id     text REFERENCES khoan(id) ON DELETE CASCADE,
  van_ban_id   text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  cap          int  NOT NULL,
  linh_vuc     text[] NOT NULL DEFAULT '{}',
  hieu_luc_tu  date, hieu_luc_den date,
  text_goc     text NOT NULL,
  text_embed   text NOT NULL,
  embedding    vector(1024),
  tsv_goc      tsvector GENERATED ALWAYS AS (to_tsvector('simple', text_goc)) STORED,
  created_at   timestamptz DEFAULT now()
);
CREATE INDEX chunk_vb ON chunk (van_ban_id, hieu_luc_den, cap);
CREATE INDEX chunk_tsv ON chunk USING gin (tsv_goc);

-- ====================== TÀI LIỆU NGƯỜI DÙNG ======================
CREATE TABLE tai_lieu (
  id               text PRIMARY KEY,             -- 'TL-<uuid8>'
  owner_id         text NOT NULL DEFAULT 'demo',
  ten              text NOT NULL,
  loai             text NOT NULL,                -- du_thao_nghi_dinh|du_thao_thong_tu|du_thao_luat|quy_che|hop_dong|khac
  cap_tuong_duong  int,                          -- cấp khi ban hành (TT=7...), NULL với quy chế/hợp đồng
  phien_ban        int  NOT NULL DEFAULT 1,
  ngay_du_kien     date,
  linh_vuc         text[] NOT NULL DEFAULT '{}',
  co_cau_truc_dieu boolean,
  can_cu_tho       text[] NOT NULL DEFAULT '{}', -- chuỗi thô từ phần Căn cứ
  can_cu_vb_ids    text[] NOT NULL DEFAULT '{}',
  loai_cay         text,                         -- ro|mo|khong
  storage_key text, hash text,
  created_at       timestamptz DEFAULT now()
);

CREATE TABLE tai_lieu_don_vi (
  id            text PRIMARY KEY,                -- 'TL-x:D5' | 'TL-x:D5:K2' | 'TL-x:P12' | 'TL-x:C3'
  tai_lieu_id   text NOT NULL REFERENCES tai_lieu(id) ON DELETE CASCADE,
  parent_id     text REFERENCES tai_lieu_don_vi(id),
  cap           text NOT NULL,                   -- dieu|khoan|diem|cum|doan
  so_dieu text, so_khoan text, diem text, tieu_de text,
  noi_dung      text NOT NULL,
  hash          text NOT NULL,
  thu_tu        int  NOT NULL,
  embedding     vector(1024)
);
CREATE INDEX don_vi_tl ON tai_lieu_don_vi (tai_lieu_id, thu_tu);
ALTER TABLE dan_chieu ADD CONSTRAINT dan_chieu_don_vi_fk
  FOREIGN KEY (nguon_don_vi_id) REFERENCES tai_lieu_don_vi(id) ON DELETE CASCADE;

-- ====================== ĐỐI CHIẾU ======================
CREATE TABLE phien_doi_chieu (
  id            text PRIMARY KEY,                -- 'PH-<uuid8>'
  tai_lieu_id   text NOT NULL REFERENCES tai_lieu(id) ON DELETE CASCADE,
  ngay_tra      date NOT NULL,
  che_do        text NOT NULL DEFAULT 'cay',     -- cay|truy_hoi|ket_hop
  tu_dong_duyet boolean NOT NULL DEFAULT false,
  buoc          text NOT NULL DEFAULT 'tao',     -- tao|cho_duyet_vb_me|tier1|cho_duyet_anh_xa|tier2|fallback|xong|loi
  loi           text,
  thong_ke      jsonb NOT NULL DEFAULT '{}',     -- so_dieu, so_mo_coi, so_phat_hien, so_goi_llm, do_tre_ms
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);

CREATE TABLE phien_van_ban_me (
  phien_id   text NOT NULL REFERENCES phien_doi_chieu(id) ON DELETE CASCADE,
  van_ban_id text NOT NULL REFERENCES van_ban(id),
  nguon      text NOT NULL,                      -- can_cu|quan_he|dan_chieu|chu_de|truy_hoi|nguoi_dung
  buoc_sau   int  NOT NULL DEFAULT 0,
  duyet      text NOT NULL DEFAULT 'de_xuat',    -- de_xuat|chap_nhan|loai_bo
  PRIMARY KEY (phien_id, van_ban_id)
);

CREATE TABLE anh_xa_dieu (
  id          serial PRIMARY KEY,
  phien_id    text NOT NULL REFERENCES phien_doi_chieu(id) ON DELETE CASCADE,
  don_vi_id   text NOT NULL REFERENCES tai_lieu_don_vi(id) ON DELETE CASCADE,  -- cấp dieu|cum
  dieu_me_id  text REFERENCES dieu_luat(id),     -- NULL = mồ côi
  loai        text NOT NULL,                     -- cu_the_hoa|dan_chieu|cung_chu_de|khong
  tin_cay     real,
  nguon       text NOT NULL,                     -- llm|dan_chieu|nguoi_dung|truy_hoi
  duyet       text NOT NULL DEFAULT 'de_xuat',
  hash_cap    text                               -- sha256(hash đơn vị | dieu_me_id | ngay) → cache tier2
);
CREATE INDEX anh_xa_phien ON anh_xa_dieu (phien_id, don_vi_id);

CREATE TABLE ket_qua_doi_chieu (
  id                 serial PRIMARY KEY,
  phien_id           text NOT NULL REFERENCES phien_doi_chieu(id) ON DELETE CASCADE,
  don_vi_id          text NOT NULL REFERENCES tai_lieu_don_vi(id) ON DELETE CASCADE,
  tang               int  NOT NULL,              -- 1 xác định | 2 LLM | 3 fallback
  loai_loi           text NOT NULL,
  muc_do             text NOT NULL,              -- cao|trung_binh|thap
  tin_cay            real,
  anh_xa_id          int REFERENCES anh_xa_dieu(id),
  can_cu_van_ban_id  text REFERENCES van_ban(id),
  can_cu_dieu_id     text REFERENCES dieu_luat(id),
  can_cu_khoan_id    text REFERENCES khoan(id),
  can_cu_trich_dan   text,                       -- nguyên văn căn cứ
  can_cu_tin_cay     text,
  doan_du_thao       text,                       -- đoạn trong dự thảo bị gắn cờ
  giai_thich         text,
  de_xuat_sua        text,
  trang_thai_ra_soat text NOT NULL DEFAULT 'moi',   -- moi|xac_nhan|bac_bo
  created_at         timestamptz DEFAULT now()
);
CREATE INDEX kq_phien ON ket_qua_doi_chieu (phien_id, loai_loi, trang_thai_ra_soat);

CREATE TABLE tier2_cache (
  hash_cap text NOT NULL, cau_hinh_hash text NOT NULL,
  ket_qua jsonb NOT NULL, created_at timestamptz DEFAULT now(),
  PRIMARY KEY (hash_cap, cau_hinh_hash)
);

CREATE TABLE chu_de_van_ban_me (                 -- gợi ý văn bản mẹ khi tài liệu không ghi Căn cứ
  loai_tai_lieu text NOT NULL, linh_vuc text NOT NULL, van_ban_id text NOT NULL REFERENCES van_ban(id),
  PRIMARY KEY (loai_tai_lieu, linh_vuc, van_ban_id)
);

-- ====================== EVAL ======================
CREATE TABLE eval_case (
  id serial PRIMARY KEY, mo_ta text,
  noi_dung_dieu text NOT NULL, tieu_de text,
  van_ban_me_ids text[] NOT NULL, ngay_tra date,
  dieu_me_mong_doi text[] NOT NULL DEFAULT '{}',
  loi_mong_doi jsonb NOT NULL DEFAULT '[]',      -- [{loai_loi, khoan_id?, so_khoan_du_thao?}]
  linh_vuc text
);
CREATE TABLE eval_run (id serial PRIMARY KEY, ten text, cau_hinh jsonb, ket_qua jsonb, chay_luc timestamptz DEFAULT now());
CREATE TABLE schema_migrations (ten text PRIMARY KEY, chay_luc timestamptz DEFAULT now());

-- ====================== HÀM ======================
CREATE OR REPLACE FUNCTION khoan_hieu_luc_tai(
  p_van_ban_id text, p_so_dieu text, p_so_khoan text, p_diem text, p_ngay date
) RETURNS khoan LANGUAGE sql STABLE AS $$
  SELECT k.* FROM khoan k JOIN dieu_luat d ON d.id = k.dieu_id
  WHERE k.van_ban_id = p_van_ban_id AND d.so_dieu = p_so_dieu AND k.so_khoan = p_so_khoan
    AND ((p_diem IS NULL AND k.diem IS NULL) OR k.diem = p_diem)
    AND k.trang_thai <> 'bai_bo'
    AND (k.hieu_luc_tu IS NULL OR k.hieu_luc_tu <= p_ngay)
    AND (k.hieu_luc_den IS NULL OR k.hieu_luc_den >= p_ngay)
  ORDER BY k.hieu_luc_tu DESC NULLS LAST LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION dieu_hieu_luc_tai(p_van_ban_id text, p_so_dieu text, p_ngay date)
RETURNS dieu_luat LANGUAGE sql STABLE AS $$
  SELECT d.* FROM dieu_luat d
  WHERE d.van_ban_id = p_van_ban_id AND d.so_dieu = p_so_dieu AND d.trang_thai <> 'bai_bo'
    AND (d.hieu_luc_tu IS NULL OR d.hieu_luc_tu <= p_ngay)
    AND (d.hieu_luc_den IS NULL OR d.hieu_luc_den >= p_ngay)
  ORDER BY d.hieu_luc_tu DESC NULLS LAST LIMIT 1;
$$;

-- bản hợp nhất: mọi Điều còn hiệu lực của một văn bản tại một ngày
CREATE OR REPLACE FUNCTION ban_hop_nhat(p_van_ban_id text, p_ngay date)
RETURNS TABLE (dieu_id text, so_dieu text, tieu_de text, tom_tat text, noi_dung text, thu_tu int,
               da_sua boolean, nguon_sua_doi_id text, tin_cay text) LANGUAGE sql STABLE AS $$
  SELECT DISTINCT ON (d.so_dieu) d.id, d.so_dieu, d.tieu_de, d.tom_tat, d.noi_dung, d.thu_tu,
         d.nguon_sua_doi_id IS NOT NULL, d.nguon_sua_doi_id, d.tin_cay
  FROM dieu_luat d
  WHERE d.van_ban_id = p_van_ban_id AND d.trang_thai <> 'bai_bo'
    AND (d.hieu_luc_tu IS NULL OR d.hieu_luc_tu <= p_ngay)
    AND (d.hieu_luc_den IS NULL OR d.hieu_luc_den >= p_ngay)
  ORDER BY d.so_dieu, d.hieu_luc_tu DESC NULLS LAST;
$$;

-- văn bản mẹ qua đồ thị: đi lên quy_dinh_chi_tiet/huong_dan/can_cu tối đa 2 bước
CREATE OR REPLACE FUNCTION van_ban_me_qua_do_thi(p_ids text[])
RETURNS TABLE (van_ban_id text, buoc_sau int) LANGUAGE sql STABLE AS $$
  WITH RECURSIVE r AS (
    SELECT unnest(p_ids) AS van_ban_id, 0 AS buoc_sau
    UNION
    SELECT q.dich_id, r.buoc_sau + 1 FROM r
    JOIN quan_he_van_ban q ON q.nguon_id = r.van_ban_id AND q.loai IN ('quy_dinh_chi_tiet','huong_dan','can_cu')
    WHERE r.buoc_sau < 2
  ) SELECT van_ban_id, min(buoc_sau) FROM r GROUP BY van_ban_id;
$$;

CREATE OR REPLACE VIEW van_ban_trang_thai_tinh AS
SELECT v.id, CASE
  WHEN v.ngay_het_hieu_luc IS NOT NULL AND v.ngay_het_hieu_luc < current_date THEN 'het_hieu_luc'
  WHEN v.ngay_hieu_luc > current_date THEN 'chua_hieu_luc'
  WHEN EXISTS (SELECT 1 FROM dieu_luat d WHERE d.van_ban_id = v.id
               AND d.trang_thai IN ('het_hieu_luc','bai_bo') AND d.thay_boi_id IS NULL) THEN 'het_hieu_luc_mot_phan'
  ELSE 'con_hieu_luc' END AS trang_thai_tinh
FROM van_ban v;

-- hybrid search (GĐ E)
CREATE OR REPLACE FUNCTION tim_kiem_hybrid(
  q_embedding vector(1024), q_text text, p_top_k int DEFAULT 20,
  p_ngay date DEFAULT current_date, p_cap_max int DEFAULT NULL,
  p_van_ban_ids text[] DEFAULT NULL, p_linh_vuc text[] DEFAULT NULL, p_k_rrf int DEFAULT 60
) RETURNS TABLE (chunk_id text, diem_rrf numeric) AS $$
WITH loc AS (
  SELECT id, embedding, tsv_goc FROM chunk
  WHERE embedding IS NOT NULL
    AND (hieu_luc_tu IS NULL OR hieu_luc_tu <= p_ngay) AND (hieu_luc_den IS NULL OR hieu_luc_den >= p_ngay)
    AND (p_cap_max IS NULL OR cap <= p_cap_max)
    AND (p_van_ban_ids IS NULL OR van_ban_id = ANY(p_van_ban_ids))
    AND (p_linh_vuc IS NULL OR linh_vuc && p_linh_vuc)),
vec AS (SELECT id, row_number() OVER (ORDER BY embedding <=> q_embedding) r FROM loc ORDER BY embedding <=> q_embedding LIMIT p_top_k*3),
bm  AS (SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv_goc, q) DESC) r FROM loc, plainto_tsquery('simple', q_text) q WHERE tsv_goc @@ q LIMIT p_top_k*3)
SELECT COALESCE(v.id,b.id), (COALESCE(1.0/(p_k_rrf+v.r),0)+COALESCE(1.0/(p_k_rrf+b.r),0))::numeric
FROM vec v FULL OUTER JOIN bm b ON v.id=b.id ORDER BY 2 DESC LIMIT p_top_k;
$$ LANGUAGE sql STABLE;
```

---

## 5. `.env.example`

```ini
DB_URL=postgresql://audit_rag:REDACTED@localhost:5433/luatvn

LLM_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:14b
LLM_API_KEY=ollama
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4000
LLM_DISABLE_THINKING=true
LLM_SONG_SONG=4

EMBED_URL=http://localhost:11434/v1        # chỉ dùng ở GĐ E
EMBED_MODEL=bge-m3
EMBED_DIM=1024
EMBED_API_KEY=ollama
EMBED_BATCH_SIZE=32
ENABLE_FALLBACK=false                       # true khi GĐ E xong

HIEU_LUC_MAC_DINH=today
AUDIT_CHE_DO_MAC_DINH=cay
AUDIT_TU_DONG_DUYET=false
AUDIT_MAX_DIEU_ME=6
AUDIT_MAX_TOKEN_PROMPT=12000
AUDIT_DIFF_NGUONG=0.92
AUDIT_NGUONG_FALLBACK=0.45
STORAGE_PATH=./data/private

API_HOST=0.0.0.0
API_PORT=8010
LOG_LEVEL=INFO
```

---

## 6. Quy ước

### 6.1 ID và phiên bản (v3.1 — model cây)
- `van_ban.id` = **id vbpl trực tiếp** (số như `66801` hoặc UUID như `2d8a8130-…`); trùng `meta.documents.id`.
- `node.id` = **UUID node của vbpl** (trường `key`/`id` trong API cây). Không ghép id thủ công; `so_thu_tu` ('5','2','a') chỉ để sắp xếp/hiển thị, không làm khóa.
- Quan hệ sửa đổi ở cấp điều khoản ghi vào `tac_dong`: `node_dich_id` (bị sửa) ← `node_nguon_id` (node ra lệnh, thuộc văn bản đi sửa). Một node bị nhiều lần sửa = nhiều dòng `tac_dong` (giữ đủ lịch sử), không version-hóa id.
- `hieu_luc_tu`/`hieu_luc_den` của node lấy từ `effFrom`/`effTo` của API. Tra Điều/Khoản theo ngày lọc trên hai cột này (hàm tra viết lại trên `node` khi dựng lại §4b).

### 6.2 Parser (giữ v2, sửa)
- Điều `^Điều\s+(\d+[a-zđ]?)\s*\.?\s*(.*)$`; Khoản `^(\d+[a-zđ]?)\.\s+`; Điểm `^([a-zđ])\)\s+`; Chương/Mục như v2. Số Điều tăng theo phần số; nhảy/trùng → WARNING, không dừng. Dòng "1." trong ngoặc kép chưa đóng không phải Khoản.
- Căn cứ: dòng `^Căn cứ\s+` đến dòng trống hoặc "Theo đề nghị". Ngày hiệu lực: Điều "Hiệu lực thi hành".
- Văn bản sửa đổi: nhận diện qua tên/Điều "Sửa đổi, bổ sung một số điều của ..."; mỗi Khoản của Điều đó là một lệnh; pattern `sua_doi | bo_sung | bai_bo | thay_cum_tu`; không khớp → ghi lệnh thô `tin_cay='can_ra_soat'` + WARNING. Parser chỉ ghi `quan_he_van_ban`, không chạm `dieu_luat`/`khoan`.
- Dẫn chiếu: `(điểm X )?(khoản N )?Điều M (của )?(Luật này|Bộ luật này|Nghị định này|Thông tư này|<tên/số hiệu>)`; "Luật này" = văn bản chứa; nhiều Điều → nhiều dòng.

### 6.3 Thi hành lệnh (`ingestion/sync.py`)
Mỗi lệnh `da_ap_dung=false` trong một transaction: sửa → bản cũ `hieu_luc_den = ngay-1`, `het_hieu_luc`, `thay_boi_id`; bản mới id `@ngay`; bổ sung → tạo mới, đánh lại `thu_tu`; bãi bỏ → `bai_bo`. Phân giải `dich_dieu_id` từ `dich_so_dieu` lúc thi hành; văn bản đích chưa nạp → `loi_ap_dung='chua_nap_van_ban_dich'`, giữ lệnh chờ. Sau đó cập nhật `van_ban.trang_thai` từ view. Chạy lại idempotent.

### 6.4 Tóm tắt Điều (`ingestion/summarize.py`)
Một câu ≤ 30 từ, nêu đối tượng và nội dung chính, không nêu số Điều. Batch 20 Điều/prompt, JSON `[{dieu_id, tom_tat}]`. Không có LLM → dùng tiêu đề + 120 ký tự đầu.

### 6.5 Đối chiếu
- **segment**: có Điều → `dieu` + `khoan/diem`; không → `^[IVX]+\.`, `^\d+\.`, `^[a-zđ]\)` → `doan`; > 30 đoạn thì LLM gom `cum` (JSON `[{ten, don_vi_ids}]`). `hash = sha256(normalize(noi_dung)|tieu_de cấp trên)`.
- **parent_docs**, thứ tự nguồn: `can_cu` (khớp số hiệu, rồi tên+năm) → `quan_he` (`van_ban_me_qua_do_thi`) → `dan_chieu` (văn bản được dẫn ≥ 2 lần) → `chu_de` (`chu_de_van_ban_me`) → `truy_hoi` (chỉ khi `ENABLE_FALLBACK`). Luật nền: có chế tài → Luật XLVPHC; là VBQPPL → Luật Ban hành VBQPPL (chỉ cho tier1 thể thức). `loai_cay`: `ro` nếu có từ nguồn 1–2, `mo` nếu chỉ 3–5, `khong` nếu rỗng → dừng, báo người dùng chọn tay.
- **consolidate**: `ban_hop_nhat(van_ban_id, ngay)`; văn bản > 300 Điều thì chia theo Chương khi làm mục lục.
- **tier1**, mọi đơn vị cấp khoản/đoạn: (a) dẫn chiếu → `khoan_hieu_luc_tai`/`dieu_hieu_luc_tai` tại `ngay_du_kien` → `ket_qua` → loai_loi tương ứng; (b) đoạn trích trong ngoặc kép hoặc sau "quy định:" → `rapidfuzz.fuzz.ratio` (sau normalize) với khoản được dẫn, < `AUDIT_DIFF_NGUONG*100` → `trich_sai_nguyen_van` kèm diff; (c) thể thức: số hiệu trong Căn cứ không khớp loại/cơ quan trong DB → `the_thuc`. Ghi `tang=1`, `tin_cay=1.0`.
- **mapping**: input mục lục dự thảo `[{id, so_dieu, tieu_de, mo_dau}]` + mục lục mẹ `[{dieu_id, ten_vb, so_dieu, tieu_de, tom_tat}]`; output `[{don_vi_id, dieu_me_ids[], loai, tin_cay}]`; validate id ∈ input; thêm ánh xạ `nguon='dan_chieu'` cho Điều dự thảo dẫn thẳng Điều mẹ; tối đa `AUDIT_MAX_DIEU_ME`. Dừng `cho_duyet_anh_xa` trừ `tu_dong_duyet`.
- **tier2**: một prompt cho một Điều dự thảo (đủ Khoản) + các Điều mẹ đã duyệt (nguyên văn, ghi rõ văn bản, cấp, "đã sửa bởi"). Output JSON mảng `{so_khoan_du_thao, loai_loi, muc_do, tin_cay, can_cu:{dieu_me_id, so_khoan, trich_dan}, giai_thich, de_xuat_sua}`; `phu_hop` không ghi DB. Validate: `dieu_me_id` ∈ ánh xạ; `trich_dan` khớp Điều mẹ (fuzz partial ≥ 85) nếu không → `tin_cay` 0.5 và ghi chú; phân giải `can_cu_khoan_id` từ `so_khoan`. `vuot_tham_quyen` chỉ khi `cap_tuong_duong` dự thảo > `cap` mẹ; ngược lại đổi `mau_thuan_truc_tiep`. Cache `tier2_cache`.
- **fallback**: khi `ENABLE_FALLBACK=false`, Điều mồ côi ghi `khong_co_can_cu_uy_quyen`, `muc_do='trung_binh'`, giải thích "không ánh xạ được tới văn bản mẹ; cần rà soát thủ công". Khi bật (GĐ E): embed từng khoản → `tim_kiem_hybrid(p_cap_max = cap dự thảo − 1)` → ứng viên ≥ ngưỡng → ánh xạ `nguon='truy_hoi'` → tier2 `tang=3`.
- **workflow**: lưu `buoc` sau mỗi bước; `tiep_tuc(phien_id)` chạy từ bước đang dừng; tier2 song song theo Điều (`LLM_SONG_SONG`); `thong_ke` cập nhật liên tục.

### 6.6 Prompt
Tiếng Việt, vai trò "chuyên viên thẩm định văn bản", `temperature` ≤ 0.1, tắt thinking, chỉ trả JSON, cắt ``` trước parse, parse lỗi → retry 1 lần kèm thông báo lỗi. Tier2 phải nhắc: "chỉ kết luận khi trích được nguyên văn căn cứ; không có thì ghi phu_hop".

### 6.7 Chung
Upsert idempotent; LLM/embedding gọi `httpx` + `tenacity` retry 3 lần; `structlog`; type hints; pydantic cho mọi dataclass; test với LLM mock (JSON cố định) + test `@pytest.mark.llm` khi có `LLM_URL`.

---

## 7. Kế hoạch theo giai đoạn

### GĐ A – Nền và nạp luật
**Mục tiêu**: `python scripts/ingest.py --file data/raw/blld2019.pdf --id BLLD-2019-45 --loai bo_luat --linh-vuc lao_dong` → `van_ban` 1, `dieu_luat` 220, `khoan` đủ, `tom_tat` có; `ban_hop_nhat('BLLD-2019-45', today)` trả 220 Điều.

| # | Task | Tiêu chí |
|---|------|----------|
| A1 | Dọn repo: xóa `migrations/` cũ, `retrieval/`, `qa/`; giữ `loader.py`, `normalize.py`, `parser.py`, `embedder.py`, `llm.py`, `config.py`; tạo cấu trúc mục 3; `.env.example` mục 5 | `python -c "from app.config import settings"` chạy |
| A2 | `migrations/001_init.sql` (mục 4) + `scripts/init_db.py` | DB mới; chạy 2 lần OK; `\df` thấy 5 hàm |
| A3 | `models/schemas.py` + sửa `parser.py`: `so_dieu: str`, trả `list[Khoan]` (Khoản+Điểm), trích Căn cứ, ngày hiệu lực, cơ quan; cờ văn bản sửa đổi | test cũ pass + ca "54a", Căn cứ, văn bản sửa đổi |
| A4 | `db/session.py`, `db/repo_van_ban.py` | upsert idempotent; `get_muc_luc(van_ban_id, ngay)` |
| A5 | `ingestion/summarize.py` | 20 Điều mẫu → 20 `tom_tat`; mock khi không có LLM |
| A6 | `ingestion/pipeline.py` + `scripts/ingest.py` | BLLĐ 2019: 220 Điều; Khoản của 3 Điều kiểm tra tay đúng; `cap`, `ngay_hieu_luc` đúng |
| A7 | `tests/data/` văn bản rút gọn; `pytest` | xanh |

### GĐ B – Hiệu lực và quan hệ
**Mục tiêu**: nạp một văn bản sửa đổi thật → `khoan_hieu_luc_tai` trả bản khác nhau trước/sau ngày hiệu lực; `van_ban_me_qua_do_thi` trả đúng luật mẹ của một nghị định.

| # | Task | Tiêu chí |
|---|------|----------|
| B1 | `ingestion/amend_parser.py`; `ingest.py` tự gọi khi `la_van_ban_sua_doi` | Lệnh khớp danh sách kỳ vọng; lệnh lạ → `can_ra_soat` + WARNING |
| B2 | `ingestion/sync.py` + `db/repo_hieu_luc.py` + `scripts/sync.py` | Idempotent; bản cũ/mới đúng theo ngày; `van_ban.trang_thai` = `het_hieu_luc_mot_phan` |
| B3 | `ingestion/citation_parser.py`; ghi `dan_chieu(nguon='luat')` khi nạp | 15 ca test; BLLĐ ≥ 90% dẫn chiếu nội bộ phân giải được |
| B4 | Quan hệ khi nạp: phần Căn cứ của NĐ/TT → `quan_he_van_ban(loai='can_cu')`; tên có "quy định chi tiết/hướng dẫn thi hành" → thêm `quy_dinh_chi_tiet` | Nạp NĐ 145/2020 → cạnh tới BLLĐ |
| B5 | `scripts/seed_demo.py`: nạp bộ demo + seed `chu_de_van_ban_me` | Một lệnh dựng xong kho demo |

### GĐ C – Đối chiếu
**Mục tiêu**: `python scripts/audit.py --file du_thao.docx --loai du_thao_thong_tu --ngay 2026-06-01 --auto` → báo cáo markdown; trên `eval_case` ≥ 40 ca: tầng 1 recall 100%, ánh xạ đúng ≥ 85%, tầng 2 recall ≥ 75% cho `doi_so_lieu`/`them_dieu_kien`/`mau_thuan_truc_tiep`, mẫu âm ≤ 1 phát hiện sai/10.

| # | Task | Tiêu chí |
|---|------|----------|
| C1 | `db/repo_tai_lieu.py`, `db/repo_audit.py`, lưu file `STORAGE_PATH` | |
| C2 | `audit/segment.py` | Dự thảo có Điều và quy chế không Điều → đơn vị đúng; `can_cu_tho` đúng |
| C3 | `audit/parent_docs.py` + `audit/consolidate.py` | 5 tài liệu mẫu → văn bản mẹ khớp kỳ vọng, `loai_cay` đúng; bản hợp nhất tại 2 ngày khác nhau |
| C4 | `audit/tier1.py` | 20 ca tiêm lỗi → recall 100%; 10 mẫu âm → 0 |
| C5 | `audit/mapping.py` + prompt | ≥ 85% trên eval; validate id |
| C6 | `audit/tier2.py` + prompt + cache | recall như mục tiêu; mọi phát hiện có căn cứ hợp lệ và `can_cu_trich_dan` khớp Điều mẹ |
| C7 | `audit/workflow.py` (dừng/duyệt/tiếp tục, song song) | 40 Điều, 3 VB mẹ: `so_goi_llm` ≤ 40 + 3; tiếp tục từ `cho_duyet_anh_xa` không chạy lại tier1 |
| C8 | `audit/report.py` + `scripts/audit.py` | Markdown: văn bản mẹ, bảng ánh xạ, phát hiện theo Điều (vị trí, loại, mức, căn cứ nguyên văn, giải thích, đề xuất), mồ côi, cờ `can_ra_soat` |
| C9 | `scripts/eval_audit.py` + seed `eval_case` (tiêm lỗi từ Điều thật của thông tư đã ban hành, mỗi loại ≥ 6 ca, ≥ 10 mẫu âm) | Bảng recall/precision theo loại trong README |
| C10 | Điều mồ côi khi `ENABLE_FALLBACK=false` | ghi `khong_co_can_cu_uy_quyen` |

### GĐ D – API và UI demo
**Mục tiêu**: mở `http://localhost:8010`, làm trọn luồng upload luật → upload dự thảo → duyệt → xem kết quả.

| # | Task | Tiêu chí |
|---|------|----------|
| D1 | `routes_van_ban.py`: `POST /van-ban` (multipart + meta), `GET /van-ban`, `GET /van-ban/{id}/dieu?ngay=`, `POST /van-ban/sync`, `GET /van-ban/{id}/quan-he` | OpenAPI |
| D2 | `routes_tai_lieu.py`: `POST /tai-lieu` (multipart + loai + ngay_du_kien), `GET /tai-lieu/{id}/don-vi` | |
| D3 | `routes_audit.py`: `POST /audit {tai_lieu_id, ngay, che_do, tu_dong_duyet}`; `GET /audit/{id}`; `PUT /audit/{id}/van-ban-me`; `PUT /audit/{id}/anh-xa`; `POST /audit/{id}/tiep-tuc`; `GET /audit/{id}/ket-qua`; `PATCH /audit/ket-qua/{id}`; `GET /audit/{id}/report.md` | test luồng dừng–duyệt–tiếp tục |
| D4 | Worker nền `asyncio`; API trả tiến độ | phiên 40 Điều không block API |
| D5 | `static/index.html`: 3 tab (Kho luật: upload, danh sách, trạng thái, Điều đã sửa; Dự thảo: upload; Đối chiếu: chọn dự thảo + ngày, chạy, duyệt VB mẹ, duyệt ánh xạ, bảng kết quả lọc theo loại/mức, bấm một phát hiện thấy đoạn dự thảo và căn cứ cạnh nhau, xác nhận/bác bỏ, tải report.md) | Demo trọn luồng không cần CLI |
| D6 | `Dockerfile` + `docker-compose.yml` (db + app) | `docker compose up` |

### GĐ E – Truy hồi dự phòng (sau demo)
E1 `ingestion/chunks.py` tạo chunk + embedding từ `khoan` (kế thừa hiệu lực, HNSW sau khi nạp); E2 `retrieval/hybrid.py`; E3 `audit/fallback.py` với `ENABLE_FALLBACK=true`; E4 nguồn `truy_hoi` trong `parent_docs`; E5 eval lại Điều mồ côi. Chatbot hỏi đáp xây trên cùng lớp này nếu cần.

---

## 8. Kịch bản demo

1. `scripts/seed_demo.py` hoặc qua UI: upload BLLĐ 2019 (bộ luật, cấp 2), NĐ 145/2020 (nghị định, cấp 5, căn cứ BLLĐ), một nghị định sửa đổi NĐ 145 (hiệu lực trước ngày demo), một thông tư hướng dẫn. Bấm "Đồng bộ hiệu lực". Tab Kho luật hiển thị NĐ 145 "hết hiệu lực một phần", bấm vào xem Điều đã sửa.
2. Upload dự thảo thông tư (soạn từ thông tư thật, cố ý tiêm 6–8 lỗi: dẫn khoản đã bị sửa, trích sai số ngày, thêm điều kiện, mức phạt vượt khung, dẫn Điều không tồn tại, thêm một Điều không có trong văn bản mẹ). Chọn ngày dự kiến.
3. Chạy đối chiếu. Màn 1: văn bản mẹ đề xuất kèm nguồn suy ra → chấp nhận. Màn 2: bảng ánh xạ Điều → sửa một dòng nếu muốn → tiếp tục.
4. Kết quả: ví dụ "Khoản 2 Điều 5 dự thảo – dan_het_hieu_luc – cao – Căn cứ: khoản 3 Điều 12 NĐ 145/2020 đã được sửa bởi NĐ xx/2026, hiệu lực dd/mm/yyyy; nội dung hiện hành: '...'". Bấm vào thấy hai đoạn cạnh nhau. Xác nhận/bác bỏ. Tải report.md.
5. Sửa dự thảo, upload lại (phiên bản 2) → chỉ Điều thay đổi chạy lại LLM (cache).

Dữ liệu demo do người dùng cung cấp: 4 văn bản thật ở bước 1 và dự thảo ở bước 2. Claude Code không tự chế.

---

## 9. Cách làm việc với Claude Code

- Trước mỗi task: đọc mục 1, 4, 6. Mỗi task một commit: `GĐC5 mapping: prompt + validate + test`.
- Test đi cùng code cho mọi parser và mọi bước audit; LLM trong test dùng mock trả JSON cố định; test thật đánh dấu `llm`/`integration`.
- Sau C4–C6, C9: chạy `scripts/eval_audit.py --save`, ghi README.
- `audit/` không viết SQL truy hồi riêng; đi qua `db/` và (GĐ E) `retrieval/`.
- Cần văn bản thật, dự thảo mẫu, danh sách văn bản mẹ mặc định: dừng và hỏi. Không bịa nội dung luật.
- Thư viện: `psycopg[binary,pool]`, `pgvector`, `pydantic`, `pydantic-settings`, `fastapi`, `uvicorn`, `python-multipart`, `python-docx`, `pymupdf`, `beautifulsoup4`, `httpx`, `tenacity`, `structlog`, `rapidfuzz`, `pytest`, `rich`. LlamaIndex không bắt buộc. Khác → hỏi.
- Cập nhật mục 10 sau mỗi task.

---

## 10. Tiến độ

| Task | Trạng thái | Ghi chú |
|------|-----------|---------|
| A1 | ✓ | 2026-10-26: cấu trúc §3, config.py, .env.example, pyproject.toml, .gitignore, README.md; verify `from app.config import settings` OK |
| A2 | ✓ | 2026-10-26: 001_init.sql + scripts/init_db.py; reset schema public; chạy 2 lần OK; đủ 17 bảng + 5 hàm + view `van_ban_trang_thai_tinh` |
| A3 | ✓ | 2026-10-26: schemas.py, normalize.py, loader.py, parser.py; 12/12 test pass |
| A4 | ✓ | 2026-10-26: db/session.py (pool), db/repo_van_ban.py (upsert idempotent, get_muc_luc, get_dieu_full); test integration pass |
| A5 | ✓ | 2026-10-26: llm.py (goi_chat/goi_json retry+cat fence), embedder.py, summarize.py (batch 20, fallback khi loi); 3 test pass |
| A6 | ✓ | 2026-10-26: nạp 5 bộ luật PDF; BLLĐ=220 Điều, BVMT=171, GD=117, TM=324, BHYT=57; cap/ngay_hl đúng; ban_hop_nhat today đủ |
| A7 | ⌛ | Chờ dữ liệu luật rút gọn (không bịa) |
| B1 | ✓ | 2026-10-26: amend_parser.py (4 pattern + fallback) + test 4/4 pass |
| B2 | ✓ | 2026-10-26: repo_hieu_luc.py (thi_hanh_lenh, cap_nhat_trang_thai) + sync.py + scripts/sync.py |
| B3 | ✓ | 2026-10-26: citation_parser; BLLĐ dẫn chiếu nội bộ 91.3% hợp lệ (104 dẫn chiếu, 95 hop_le, 9 khong_xac_dinh) — vượt ngưỡng 90% |
| B4 | ✓ | 2026-10-26: quan_he.py (can_cu + quy_dinh_chi_tiet); wire vào pipeline |
| B5 | ⌛ | scripts/seed_demo.py code xong; chờ YAML+file luật thật |
| C1 | ✓ | 2026-10-26: repo_tai_lieu.py, repo_audit.py (phien, vb me, anh xa, ket qua, cache) |
| C2 | ✓ | 2026-10-26: audit/segment.py; test 2/2 pass |
| C3 | ⌛ | parent_docs.py + consolidate.py code xong; verify 5 tài liệu mẫu chờ user |
| C4 | ⌛ | tier1.py code xong; verify 20 ca tiêm lỗi chờ data |
| C5 | ⌛ | mapping.py + prompts.py code xong; verify ≥85% eval chờ data |
| C6 | ✓ | 2026-10-26: tier2.py refactor sang **cấp Khoản** với focus embedding (chay_tier2_cho_khoan). Verify du_thao_01: 4/7 lỗi lớn bắt đúng với căn cứ nguyên văn, 0 false positive. |
| C6-focus | ✓ | 2026-10-26: audit/focus_khoan.py — hybrid retrieval (BM25+embedding) chọn top-5 Khoản mẹ cho mỗi Khoản dự thảo, kèm ngữ cảnh Khoản liền kề |
| C7 | ✓ | workflow.py (dừng/duyệt/tiếp tục + song song LLM_SONG_SONG) |
| C8 | ✓ | report.py + scripts/audit.py |
| C9 | ⌛ | scripts/eval_audit.py code xong; cần eval_case seed |
| C10 | ✓ | fallback.py: ENABLE_FALLBACK=false → khong_co_can_cu_uy_quyen |
| D1 | ✓ | 2026-10-26: routes_van_ban (upload, list, muc_luc, sync, quan_he) |
| D2 | ✓ | 2026-10-26: routes_tai_lieu (upload+segment, don_vi, list) |
| D3 | ✓ | 2026-10-26: routes_audit (POST+GET phien, PUT vb_me+anh_xa, tiep_tuc, ket_qua, PATCH, report.md) |
| D4 | ✓ | Worker nền qua `BackgroundTasks` + `tiep_tuc()`; API trả tiến độ qua `GET /audit/{id}` |
| D5 | ✓ | static/index.html — 3 tab, demo không cần CLI |
| D6 | ✓ | Dockerfile (python 3.11 + libpq) + docker-compose (db+app) |
| E1 | ✓ | ingestion/chunks.py — tạo chunk + embedding từ Khoan/Dieu, idempotent |
| E2 | ✓ | retrieval/hybrid.py — gọi `tim_kiem_hybrid()`, embed từ text |
| E3 | ✓ | audit/fallback.py — khi ENABLE_FALLBACK=true gọi hybrid tìm ứng viên |
| E4 | ✓ | parent_docs._tim_vb_qua_truy_hoi(): nguồn `truy_hoi` khi ENABLE_FALLBACK=true |
| E5 | ⌛ | scripts/embed_all.py code xong; verify + eval mồ côi chờ data thật |
| V3.1-schema | ✓ | 2026-11-02: pivot kho pháp luật sang model CÂY từ API vbpl. `003_public_cay.sql`: drop toàn bộ public cũ (kho + audit + eval + 5 hàm), dựng `van_ban`/`node`/`tac_dong`/`chunk` + view `v_dieu`/`v_khoan`, khóa = UUID vbpl, FK `van_ban→meta.documents`. doc_api thêm `fetch_cay_noidung` (31572a1d) + `parse_rsc_flight`/`resolve_rsc_refs`; scripts/fetch_cay_dieu.py. §4 PLAN cập nhật; app/ingestion+audit (bám schema cũ) CHỜ viết lại |
| V3.1-loader | ✓ | 2026-11-02: `store_public.save_cay` (flatten cây→node, sinh chunk node lá, upsert van_ban từ meta) + CLI `crawl_vbpl.py build-cay` + test 5/5. Nạp 13 VB trong crawl_queue: node=4388, chunk=3367, 0 mồ côi |
| V3.1-phan | ✓ | 2026-11-02: migration 004 thêm cấp `phan` (Part > Chapter) vào enum cap_node; loader map `Part→phan`, prefix 'P', regex "Phần thứ/số"; sửa lỗi level lạ bỏ cả nhánh → nay giữ con. Test 6/6 |
| V3.1-amend | ⌛ | parse lệnh sửa đổi từ văn bản đi sửa → ghi `tac_dong` (node_dich←node_nguon); chưa làm |
| V3.2-split | ✓ | 2026-11-03: tách `app/` thành **2 service** (chung repo) + package lõi: `app/core` (config, db/session, models, html_text) · `app/crawl` (ghi meta, nơi duy nhất gọi vbpl.vn; lệnh `fetch-cay`→`meta.document_cay`) · `app/doisanh` (đọc/ghi public, đối sánh; `public_loader.build_cay_tu_meta` + CLI `build-cay` đọc meta→public, không gọi mạng). Migration `005_meta_cay.sql`. 2 Dockerfile + compose. Bất biến: crawl↔doisanh không import lẫn nhau, chỉ qua core. 33/33 test pass |