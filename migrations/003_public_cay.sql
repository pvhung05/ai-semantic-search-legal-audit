-- =====================================================================
-- 003: Dung lai schema `public` theo CAY noi dung lay tu API vbpl.vn.
--
-- Thay model v3 cu (id ghep 'VB:D5:K2', tach dieu_luat/khoan) bang MOT bang
-- `node` thong nhat (adjacency list) cho Chuong/Muc/Dieu/Khoan/Diem, khoa = UUID
-- cua vbpl. Lien ket sua doi o CAP DIEU KHOAN nam o `tac_dong` (node_dich <- node_nguon).
--
-- Drop toan bo public cu (kho phap luat + audit + eval). Giu lai pgvector va
-- bang schema_migrations. Metadata van ban dung lai o schema `meta`.
-- Chay 1 lan (init_db.py ghi nhan theo ten file).
-- =====================================================================

BEGIN;

-- ---------- 1) Go ham + view nghiep vu cu (GIU nguyen ham cua pgvector) ----------
DROP FUNCTION IF EXISTS ban_hop_nhat CASCADE;
DROP FUNCTION IF EXISTS dieu_hieu_luc_tai CASCADE;
DROP FUNCTION IF EXISTS khoan_hieu_luc_tai CASCADE;
DROP FUNCTION IF EXISTS van_ban_me_qua_do_thi CASCADE;
DROP FUNCTION IF EXISTS tim_kiem_hybrid CASCADE;
DROP VIEW     IF EXISTS van_ban_trang_thai_tinh CASCADE;

-- ---------- 2) Drop bang cu (CASCADE de go het FK phu thuoc) ----------
DROP TABLE IF EXISTS
  ket_qua_doi_chieu, anh_xa_dieu, phien_van_ban_me, phien_doi_chieu,
  tier2_cache, chu_de_van_ban_me, eval_run, eval_case,
  dan_chieu, tai_lieu_don_vi, tai_lieu,
  chunk, quan_he_van_ban, khoan, dieu_luat, van_ban
  CASCADE;

-- ---------- 3) Kieu enum ----------
CREATE EXTENSION IF NOT EXISTS vector;

DROP TYPE IF EXISTS cap_node CASCADE;
DROP TYPE IF EXISTS trangthai_node CASCADE;
DROP TYPE IF EXISTS loai_tacdong CASCADE;

CREATE TYPE cap_node       AS ENUM ('chuong','muc','dieu','khoan','diem');
CREATE TYPE trangthai_node AS ENUM
  ('chua_hieu_luc','con_hieu_luc','het_hieu_luc_mot_phan','het_hieu_luc','bai_bo','khong_xac_dinh');
CREATE TYPE loai_tacdong   AS ENUM
  ('sua_doi','bo_sung','bai_bo','thay_the','dinh_chi','huong_dan','thay_cum_tu');

-- ---------- 4) Van ban: dung lai metadata da crawl o meta.documents ----------
CREATE TABLE van_ban (
  id                text PRIMARY KEY REFERENCES meta.documents(id) ON DELETE CASCADE, -- = vbpl id
  so_hieu           text,
  ten               text,
  loai              text,
  ngay_ban_hanh     date,
  ngay_hieu_luc     date,
  ngay_het_hieu_luc date,
  trang_thai        trangthai_node NOT NULL DEFAULT 'khong_xac_dinh',
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------- 5) CAY noi dung: 1 dong = 1 node = don vi chunk ----------
CREATE TABLE node (
  id           text PRIMARY KEY,                                   -- UUID node tu API (key/id)
  van_ban_id   text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  parent_id    text REFERENCES node(id) ON DELETE CASCADE,         -- cay cha-con
  cap          cap_node NOT NULL,                                  -- map tu level
  ptype        smallint,                                           -- ma cap goc vbpl (2,5,...)
  so_thu_tu    text,                                               -- '5','2','a' (parse tu title)
  tieu_de      text,                                               -- title
  noi_dung     text,                                               -- content.content (HTML, node la)
  order_index  int,                                                -- orderIndex phang
  is_leaf      boolean NOT NULL DEFAULT false,
  duong_dan    text,                                               -- 'D5>K2>Da' de tra nhanh
  hieu_luc_tu  date,                                               -- effFrom
  hieu_luc_den date,                                               -- effTo
  trang_thai   trangthai_node NOT NULL DEFAULT 'khong_xac_dinh',
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX node_vb     ON node (van_ban_id, order_index);
CREATE INDEX node_parent ON node (parent_id);
CREATE INDEX node_tra    ON node (van_ban_id, cap, so_thu_tu);

-- ---------- 6) TAC DONG cap dieu khoan: node bi sua <- node di sua (xuyen van ban) ----------
CREATE TABLE tac_dong (
  id               bigserial PRIMARY KEY,
  node_dich_id     text NOT NULL REFERENCES node(id) ON DELETE CASCADE,  -- Dieu/Khoan BI tac dong
  node_nguon_id    text REFERENCES node(id) ON DELETE SET NULL,          -- Dieu/Khoan DI tac dong (lenh)
  van_ban_nguon_id text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  loai             loai_tacdong NOT NULL,
  ngay_hieu_luc    date,
  cum_tu_cu        text,
  cum_tu_moi       text,
  noi_dung_moi     text,
  nguon_lenh       text,                                                 -- nguyen van lenh trich tu luat sua
  tin_cay          text NOT NULL DEFAULT 'can_ra_soat',                  -- xac_nhan | can_ra_soat
  da_ap_dung       boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tacdong_dich  ON tac_dong (node_dich_id, loai);
CREATE INDEX tacdong_nguon ON tac_dong (node_nguon_id);
CREATE INDEX tacdong_vbnguon ON tac_dong (van_ban_nguon_id);

-- ---------- 7) CHUNK dan xuat cho RAG (tach node dai thanh nhieu mau khi can) ----------
CREATE TABLE chunk (
  id           bigserial PRIMARY KEY,
  node_id      text NOT NULL REFERENCES node(id) ON DELETE CASCADE,
  van_ban_id   text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  thu_tu       int  NOT NULL DEFAULT 0,                             -- neu 1 node tach nhieu chunk
  text_goc     text NOT NULL,
  text_embed   text,
  embedding    vector(1024),
  tsv_goc      tsvector GENERATED ALWAYS AS (to_tsvector('simple', text_goc)) STORED,
  hieu_luc_tu  date,
  hieu_luc_den date,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chunk_node ON chunk (node_id);
CREATE INDEX chunk_vb   ON chunk (van_ban_id, hieu_luc_den);
CREATE INDEX chunk_tsv  ON chunk USING gin (tsv_goc);
-- HNSW cho chunk.embedding tao sau khi nap (GD embedding), khong trong migration.

-- ---------- 8) VIEW tien dung doc theo tung cap (khong mat loi ich 1 bang) ----------
CREATE VIEW v_dieu AS
  SELECT id, van_ban_id, parent_id, so_thu_tu AS so_dieu, tieu_de, noi_dung,
         order_index, hieu_luc_tu, hieu_luc_den, trang_thai
  FROM node WHERE cap = 'dieu';

CREATE VIEW v_khoan AS
  SELECT id, van_ban_id, parent_id, so_thu_tu AS so_khoan, tieu_de, noi_dung,
         order_index, hieu_luc_tu, hieu_luc_den, trang_thai
  FROM node WHERE cap IN ('khoan','diem');

COMMIT;
