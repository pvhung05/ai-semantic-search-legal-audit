-- Bang cay tho (JSON) cua noi dung van ban, do service CRAWL ghi.
-- Service crawl la noi DUY NHAT goi API vbpl.vn: lenh `fetch-cay` luu cay noi dung
-- (ket qua doc_api.fetch_cay_noidung) vao day. Service DOI SANH doc cay tu bang nay
-- de dung `public.node`/`public.chunk` (public_loader.build_cay_tu_meta) ma khong goi mang.

CREATE TABLE IF NOT EXISTS meta.document_cay (
  document_id text PRIMARY KEY REFERENCES meta.documents(id) ON DELETE CASCADE,
  cay         jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
