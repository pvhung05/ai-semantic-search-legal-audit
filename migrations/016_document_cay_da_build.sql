-- Trang thai da build cay (public node/chunk) cho tung van ban trong vanban.document_cay.
-- build-cay (khong --id) chi xu ly cac dong da_build=false -> khong build lai cai da xong.
ALTER TABLE vanban.document_cay
    ADD COLUMN IF NOT EXISTS da_build boolean NOT NULL DEFAULT false;

-- Danh dau nhung van ban DA co node (build truoc khi co cot nay) de khoi build lai.
UPDATE vanban.document_cay c
   SET da_build = true
 WHERE EXISTS (SELECT 1 FROM vanban.node n WHERE n.van_ban_id = c.document_id);
