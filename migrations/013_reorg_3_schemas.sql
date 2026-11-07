-- 013: To chuc lai thanh 3 schema (cung 1 database):
--   danhmuc : danh muc dung chung (ca crawl lan doi sanh doc)
--   vanban  : du lieu & cau truc phap luat (= meta cu doi ten + van_ban/node/tac_dong)
--   rag     : chunk + vector (chunk, du_thao, du_thao_node)
-- public giu lai cho extension pgvector + schema_migrations.
--
-- Dung ALTER ... SET SCHEMA / RENAME -> giu nguyen DU LIEU va FK (FK tu dong theo OID).
-- 2 ham co body hardcode schema (tim_kiem_hybrid: public.chunk; impacts_cho_node) -> tao lai.

CREATE SCHEMA IF NOT EXISTS danhmuc;
CREATE SCHEMA IF NOT EXISTS rag;

-- 1) meta -> vanban (keo theo moi bang/view/enum/func cua meta)
ALTER SCHEMA meta RENAME TO vanban;
DROP TYPE IF EXISTS vanban.cap_dieukhoan;   -- enum mo coi (document_articles da drop o 012)

-- 2) Danh muc vanban -> danhmuc
ALTER TABLE vanban.loai_vanban    SET SCHEMA danhmuc;
ALTER TABLE vanban.coquan_banhanh SET SCHEMA danhmuc;
ALTER TABLE vanban.nganh          SET SCHEMA danhmuc;
ALTER TABLE vanban.linhvuc        SET SCHEMA danhmuc;
ALTER TABLE vanban.chucdanh       SET SCHEMA danhmuc;
ALTER TABLE vanban.relation_types SET SCHEMA danhmuc;

-- 3) Cau truc phap luat public -> vanban (bang + enum + view)
ALTER TABLE public.van_ban  SET SCHEMA vanban;
ALTER TABLE public.node     SET SCHEMA vanban;
ALTER TABLE public.tac_dong SET SCHEMA vanban;
ALTER TYPE  public.cap_node       SET SCHEMA vanban;
ALTER TYPE  public.trangthai_node SET SCHEMA vanban;
ALTER TYPE  public.loai_tacdong   SET SCHEMA vanban;
ALTER VIEW  public.v_dieu        SET SCHEMA vanban;
ALTER VIEW  public.v_khoan       SET SCHEMA vanban;
ALTER VIEW  public.v_node_chunk  SET SCHEMA vanban;

-- 4) RAG public -> rag
ALTER TABLE public.chunk        SET SCHEMA rag;
ALTER TABLE public.du_thao      SET SCHEMA rag;
ALTER TABLE public.du_thao_node SET SCHEMA rag;

-- 5) Tao lai 2 ham (body cu tham chieu schema cu)
DROP FUNCTION IF EXISTS public.impacts_cho_node(text) CASCADE;
CREATE OR REPLACE FUNCTION vanban.impacts_cho_node(p_node_id text)
RETURNS SETOF vanban.tac_dong LANGUAGE sql STABLE AS $$
    WITH ref AS (SELECT van_ban_id, duong_dan FROM vanban.node WHERE id = p_node_id)
    SELECT td.* FROM vanban.tac_dong td
    JOIN vanban.node nd ON nd.id = td.node_dich_id
    JOIN ref ON nd.van_ban_id = ref.van_ban_id
    WHERE ref.duong_dan = nd.duong_dan
       OR ref.duong_dan LIKE nd.duong_dan || '>%'
       OR nd.duong_dan  LIKE ref.duong_dan || '>%';
$$;

DROP FUNCTION IF EXISTS public.tim_kiem_hybrid CASCADE;
CREATE OR REPLACE FUNCTION rag.tim_kiem_hybrid(
  q_embedding public.vector(1024), q_text text, p_top_k int DEFAULT 20,
  p_ngay date DEFAULT current_date, p_cap_max int DEFAULT NULL,
  p_van_ban_ids text[] DEFAULT NULL, p_linh_vuc text[] DEFAULT NULL, p_k_rrf int DEFAULT 60
) RETURNS TABLE (chunk_id bigint, diem_rrf numeric) AS $$
WITH loc AS (
  SELECT id, embedding, tsv_goc FROM rag.chunk
  WHERE embedding IS NOT NULL
    AND (hieu_luc_tu IS NULL OR hieu_luc_tu <= p_ngay)
    AND (hieu_luc_den IS NULL OR hieu_luc_den >= p_ngay)
    AND (p_van_ban_ids IS NULL OR van_ban_id = ANY(p_van_ban_ids))),
vec AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> q_embedding) r
  FROM loc ORDER BY embedding <=> q_embedding LIMIT p_top_k*3),
bm AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv_goc, q) DESC) r
  FROM loc, plainto_tsquery('simple', q_text) q
  WHERE tsv_goc @@ q LIMIT p_top_k*3)
SELECT COALESCE(v.id, b.id),
       (COALESCE(1.0/(p_k_rrf+v.r), 0) + COALESCE(1.0/(p_k_rrf+b.r), 0))::numeric
FROM vec v FULL OUTER JOIN bm b ON v.id = b.id
ORDER BY 2 DESC LIMIT p_top_k;
$$ LANGUAGE sql STABLE;

-- 6) search_path mac dinh cho moi ket noi moi (public cuoi: giu pgvector + schema_migrations)
DO $$ BEGIN
  EXECUTE format('ALTER DATABASE %I SET search_path TO vanban, danhmuc, rag, public',
                 current_database());
END $$;
