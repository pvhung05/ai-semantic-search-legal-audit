-- audit_rag v3 - schema goc theo PLAN muc 4
CREATE EXTENSION IF NOT EXISTS vector;

-- ====================== KHO PHAP LUAT (nguon su that) ======================
CREATE TABLE IF NOT EXISTS van_ban (
  id               text PRIMARY KEY,
  so_hieu          text NOT NULL UNIQUE,
  ten              text NOT NULL,
  loai             text NOT NULL,
  cap              int  NOT NULL,
  co_quan_ban_hanh text,
  ngay_ban_hanh    date,
  ngay_hieu_luc    date,
  ngay_het_hieu_luc date,
  ly_do_het        text,
  trang_thai       text NOT NULL DEFAULT 'con_hieu_luc'
     CHECK (trang_thai IN ('chua_hieu_luc','con_hieu_luc','het_hieu_luc_mot_phan','het_hieu_luc')),
  la_van_ban_sua_doi boolean NOT NULL DEFAULT false,
  linh_vuc         text[] NOT NULL DEFAULT '{}',
  tin_cay          text NOT NULL DEFAULT 'can_ra_soat',
  nguon_file       text,
  created_at       timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dieu_luat (
  id               text PRIMARY KEY,
  van_ban_id       text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  so_dieu          text NOT NULL,
  so_dieu_num      int  NOT NULL,
  chuong_so text, chuong_ten text, muc_so text, muc_ten text,
  tieu_de          text,
  noi_dung         text NOT NULL,
  tom_tat          text,
  thu_tu           int  NOT NULL,
  trang_thai       text NOT NULL DEFAULT 'con_hieu_luc',
  hieu_luc_tu      date,
  hieu_luc_den     date,
  thay_boi_id      text REFERENCES dieu_luat(id),
  nguon_sua_doi_id text REFERENCES van_ban(id),
  tin_cay          text NOT NULL DEFAULT 'can_ra_soat'
);
CREATE UNIQUE INDEX IF NOT EXISTS dieu_luat_vb_so_tu
  ON dieu_luat (van_ban_id, so_dieu, COALESCE(hieu_luc_tu, '1900-01-01'));
CREATE INDEX IF NOT EXISTS dieu_luat_vb_thutu ON dieu_luat (van_ban_id, thu_tu);

CREATE TABLE IF NOT EXISTS khoan (
  id               text PRIMARY KEY,
  dieu_id          text NOT NULL REFERENCES dieu_luat(id) ON DELETE CASCADE,
  van_ban_id       text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  so_khoan         text NOT NULL,
  diem             text,
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
CREATE INDEX IF NOT EXISTS khoan_dieu ON khoan (dieu_id, thu_tu);
CREATE INDEX IF NOT EXISTS khoan_tra ON khoan (van_ban_id, so_khoan, diem, hieu_luc_den);

CREATE TABLE IF NOT EXISTS quan_he_van_ban (
  id             serial PRIMARY KEY,
  nguon_id       text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  dich_id        text NOT NULL REFERENCES van_ban(id) ON DELETE CASCADE,
  loai           text NOT NULL CHECK (loai IN
     ('sua_doi','bo_sung','thay_the','bai_bo','huong_dan','quy_dinh_chi_tiet','can_cu','thay_cum_tu')),
  dich_dieu_id   text REFERENCES dieu_luat(id),
  dich_khoan_id  text REFERENCES khoan(id),
  dich_so_dieu   text, dich_so_khoan text, dich_diem text,
  vi_tri         text,
  ngay_hieu_luc  date,
  noi_dung_moi   text,
  cum_tu_cu text, cum_tu_moi text,
  nguon_lenh     text,
  tin_cay        text NOT NULL DEFAULT 'can_ra_soat',
  da_ap_dung     boolean NOT NULL DEFAULT false,
  loi_ap_dung    text,
  created_at     timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS quan_he_dich ON quan_he_van_ban (dich_id, loai, da_ap_dung);
CREATE INDEX IF NOT EXISTS quan_he_nguon ON quan_he_van_ban (nguon_id);

CREATE TABLE IF NOT EXISTS dan_chieu (
  id              serial PRIMARY KEY,
  nguon           text NOT NULL,
  nguon_khoan_id  text REFERENCES khoan(id) ON DELETE CASCADE,
  nguon_don_vi_id text,
  text_dan        text NOT NULL,
  so_hieu text, ten_van_ban text, so_dieu text, so_khoan text, diem text,
  van_ban_id      text REFERENCES van_ban(id),
  dieu_id         text REFERENCES dieu_luat(id),
  khoan_id        text REFERENCES khoan(id),
  ket_qua         text,
  ngay_tra        date
);
CREATE INDEX IF NOT EXISTS dan_chieu_khoan ON dan_chieu (nguon_khoan_id);
CREATE INDEX IF NOT EXISTS dan_chieu_don_vi ON dan_chieu (nguon_don_vi_id);

-- ====================== DAN XUAT (GD E, truy hoi du phong) ======================
CREATE TABLE IF NOT EXISTS chunk (
  id           text PRIMARY KEY,
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
CREATE INDEX IF NOT EXISTS chunk_vb ON chunk (van_ban_id, hieu_luc_den, cap);
CREATE INDEX IF NOT EXISTS chunk_tsv ON chunk USING gin (tsv_goc);

-- ====================== TAI LIEU NGUOI DUNG ======================
CREATE TABLE IF NOT EXISTS tai_lieu (
  id               text PRIMARY KEY,
  owner_id         text NOT NULL DEFAULT 'demo',
  ten              text NOT NULL,
  loai             text NOT NULL,
  cap_tuong_duong  int,
  phien_ban        int  NOT NULL DEFAULT 1,
  ngay_du_kien     date,
  linh_vuc         text[] NOT NULL DEFAULT '{}',
  co_cau_truc_dieu boolean,
  can_cu_tho       text[] NOT NULL DEFAULT '{}',
  can_cu_vb_ids    text[] NOT NULL DEFAULT '{}',
  loai_cay         text,
  storage_key text, hash text,
  created_at       timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tai_lieu_don_vi (
  id            text PRIMARY KEY,
  tai_lieu_id   text NOT NULL REFERENCES tai_lieu(id) ON DELETE CASCADE,
  parent_id     text REFERENCES tai_lieu_don_vi(id),
  cap           text NOT NULL,
  so_dieu text, so_khoan text, diem text, tieu_de text,
  noi_dung      text NOT NULL,
  hash          text NOT NULL,
  thu_tu        int  NOT NULL,
  embedding     vector(1024)
);
CREATE INDEX IF NOT EXISTS don_vi_tl ON tai_lieu_don_vi (tai_lieu_id, thu_tu);

-- FK tu dan_chieu.nguon_don_vi_id ve tai_lieu_don_vi (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'dan_chieu_don_vi_fk'
  ) THEN
    ALTER TABLE dan_chieu ADD CONSTRAINT dan_chieu_don_vi_fk
      FOREIGN KEY (nguon_don_vi_id) REFERENCES tai_lieu_don_vi(id) ON DELETE CASCADE;
  END IF;
END$$;

-- ====================== DOI CHIEU ======================
CREATE TABLE IF NOT EXISTS phien_doi_chieu (
  id            text PRIMARY KEY,
  tai_lieu_id   text NOT NULL REFERENCES tai_lieu(id) ON DELETE CASCADE,
  ngay_tra      date NOT NULL,
  che_do        text NOT NULL DEFAULT 'cay',
  tu_dong_duyet boolean NOT NULL DEFAULT false,
  buoc          text NOT NULL DEFAULT 'tao',
  loi           text,
  thong_ke      jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS phien_van_ban_me (
  phien_id   text NOT NULL REFERENCES phien_doi_chieu(id) ON DELETE CASCADE,
  van_ban_id text NOT NULL REFERENCES van_ban(id),
  nguon      text NOT NULL,
  buoc_sau   int  NOT NULL DEFAULT 0,
  duyet      text NOT NULL DEFAULT 'de_xuat',
  PRIMARY KEY (phien_id, van_ban_id)
);

CREATE TABLE IF NOT EXISTS anh_xa_dieu (
  id          serial PRIMARY KEY,
  phien_id    text NOT NULL REFERENCES phien_doi_chieu(id) ON DELETE CASCADE,
  don_vi_id   text NOT NULL REFERENCES tai_lieu_don_vi(id) ON DELETE CASCADE,
  dieu_me_id  text REFERENCES dieu_luat(id),
  loai        text NOT NULL,
  tin_cay     real,
  nguon       text NOT NULL,
  duyet       text NOT NULL DEFAULT 'de_xuat',
  hash_cap    text
);
CREATE INDEX IF NOT EXISTS anh_xa_phien ON anh_xa_dieu (phien_id, don_vi_id);

CREATE TABLE IF NOT EXISTS ket_qua_doi_chieu (
  id                 serial PRIMARY KEY,
  phien_id           text NOT NULL REFERENCES phien_doi_chieu(id) ON DELETE CASCADE,
  don_vi_id          text NOT NULL REFERENCES tai_lieu_don_vi(id) ON DELETE CASCADE,
  tang               int  NOT NULL,
  loai_loi           text NOT NULL,
  muc_do             text NOT NULL,
  tin_cay            real,
  anh_xa_id          int REFERENCES anh_xa_dieu(id),
  can_cu_van_ban_id  text REFERENCES van_ban(id),
  can_cu_dieu_id     text REFERENCES dieu_luat(id),
  can_cu_khoan_id    text REFERENCES khoan(id),
  can_cu_trich_dan   text,
  can_cu_tin_cay     text,
  doan_du_thao       text,
  giai_thich         text,
  de_xuat_sua        text,
  trang_thai_ra_soat text NOT NULL DEFAULT 'moi',
  created_at         timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kq_phien ON ket_qua_doi_chieu (phien_id, loai_loi, trang_thai_ra_soat);

CREATE TABLE IF NOT EXISTS tier2_cache (
  hash_cap text NOT NULL, cau_hinh_hash text NOT NULL,
  ket_qua jsonb NOT NULL, created_at timestamptz DEFAULT now(),
  PRIMARY KEY (hash_cap, cau_hinh_hash)
);

CREATE TABLE IF NOT EXISTS chu_de_van_ban_me (
  loai_tai_lieu text NOT NULL,
  linh_vuc      text NOT NULL,
  van_ban_id    text NOT NULL REFERENCES van_ban(id),
  PRIMARY KEY (loai_tai_lieu, linh_vuc, van_ban_id)
);

-- ====================== EVAL ======================
CREATE TABLE IF NOT EXISTS eval_case (
  id serial PRIMARY KEY, mo_ta text,
  noi_dung_dieu text NOT NULL, tieu_de text,
  van_ban_me_ids text[] NOT NULL, ngay_tra date,
  dieu_me_mong_doi text[] NOT NULL DEFAULT '{}',
  loi_mong_doi jsonb NOT NULL DEFAULT '[]',
  linh_vuc text
);
CREATE TABLE IF NOT EXISTS eval_run (
  id serial PRIMARY KEY, ten text, cau_hinh jsonb, ket_qua jsonb,
  chay_luc timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  ten text PRIMARY KEY, chay_luc timestamptz DEFAULT now()
);

-- ====================== HAM ======================
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

CREATE OR REPLACE FUNCTION van_ban_me_qua_do_thi(p_ids text[])
RETURNS TABLE (van_ban_id text, buoc_sau int) LANGUAGE sql STABLE AS $$
  WITH RECURSIVE r AS (
    SELECT unnest(p_ids) AS van_ban_id, 0 AS buoc_sau
    UNION
    SELECT q.dich_id, r.buoc_sau + 1 FROM r
    JOIN quan_he_van_ban q ON q.nguon_id = r.van_ban_id
      AND q.loai IN ('quy_dinh_chi_tiet','huong_dan','can_cu')
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

CREATE OR REPLACE FUNCTION tim_kiem_hybrid(
  q_embedding vector(1024), q_text text, p_top_k int DEFAULT 20,
  p_ngay date DEFAULT current_date, p_cap_max int DEFAULT NULL,
  p_van_ban_ids text[] DEFAULT NULL, p_linh_vuc text[] DEFAULT NULL, p_k_rrf int DEFAULT 60
) RETURNS TABLE (chunk_id text, diem_rrf numeric) AS $$
WITH loc AS (
  SELECT id, embedding, tsv_goc FROM chunk
  WHERE embedding IS NOT NULL
    AND (hieu_luc_tu IS NULL OR hieu_luc_tu <= p_ngay)
    AND (hieu_luc_den IS NULL OR hieu_luc_den >= p_ngay)
    AND (p_cap_max IS NULL OR cap <= p_cap_max)
    AND (p_van_ban_ids IS NULL OR van_ban_id = ANY(p_van_ban_ids))
    AND (p_linh_vuc IS NULL OR linh_vuc && p_linh_vuc)),
vec AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> q_embedding) r
  FROM loc ORDER BY embedding <=> q_embedding LIMIT p_top_k*3),
bm  AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv_goc, q) DESC) r
  FROM loc, plainto_tsquery('simple', q_text) q
  WHERE tsv_goc @@ q LIMIT p_top_k*3)
SELECT COALESCE(v.id, b.id),
       (COALESCE(1.0/(p_k_rrf+v.r), 0) + COALESCE(1.0/(p_k_rrf+b.r), 0))::numeric
FROM vec v FULL OUTER JOIN bm b ON v.id = b.id
ORDER BY 2 DESC LIMIT p_top_k;
$$ LANGUAGE sql STABLE;
