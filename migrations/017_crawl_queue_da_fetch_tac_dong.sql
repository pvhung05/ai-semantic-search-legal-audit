-- Trang thai da fetch tac dong cap dieu khoan cho tung van ban trong queue.
-- fetch-tac-dong (khong --id) chi xu ly cac dong da_fetch_tac_dong=false.
-- Can cot rieng vi van ban KHONG co tac dong nao se khong co dong trong provision_impacts
-- -> khong the dua vao EXISTS de biet "da fetch chua".
ALTER TABLE vanban.crawl_queue
    ADD COLUMN IF NOT EXISTS da_fetch_tac_dong boolean NOT NULL DEFAULT false;

-- Backfill: van ban da co cay (document_cay) la da qua 1 luot crawl-full/fetch day du
-- (cay va tac dong fetch cung dot) -> danh dau da fetch de khoi quet lai toan bo DB.
-- Van ban moi (chua co cay) giu false. Dung `--all` neu muon ep fetch lai.
UPDATE vanban.crawl_queue q
   SET da_fetch_tac_dong = true
 WHERE EXISTS (SELECT 1 FROM vanban.document_cay c WHERE c.document_id = q.id_ref);
