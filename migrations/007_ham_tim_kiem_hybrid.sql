-- 007: Dung lai ham tim_kiem_hybrid cho schema CAY (public.chunk: node_id, khong con cap/linh_vuc/dieu_id).
-- 003 da DROP ham nay ma chua tao lai. Hybrid = vector (cosine <=>) + BM25 (ts_rank_cd) hop nhat bang RRF.
-- Giu nguyen chu ky tham so de app/doisanh/retrieval/hybrid.py goi khong doi.
-- p_cap_max, p_linh_vuc giu lai cho tuong thich vi tri goi nhung KHONG ap dung (chunk cay khong gan 2 thuoc tinh nay).
DROP FUNCTION IF EXISTS tim_kiem_hybrid CASCADE;

CREATE OR REPLACE FUNCTION tim_kiem_hybrid(
  q_embedding vector(1024), q_text text, p_top_k int DEFAULT 20,
  p_ngay date DEFAULT current_date, p_cap_max int DEFAULT NULL,
  p_van_ban_ids text[] DEFAULT NULL, p_linh_vuc text[] DEFAULT NULL, p_k_rrf int DEFAULT 60
) RETURNS TABLE (chunk_id bigint, diem_rrf numeric) AS $$
WITH loc AS (
  SELECT id, embedding, tsv_goc FROM public.chunk
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
