-- 018: Tao chi muc vector HNSW cho cot embedding tren rag.chunk
-- Giup tang toc truy van khoang cach cosine (<=>) trong tim_kiem_hybrid tu O(N) xuong O(log N).
CREATE INDEX IF NOT EXISTS chunk_embedding_hnsw
ON rag.chunk USING hnsw (embedding public.vector_cosine_ops);
