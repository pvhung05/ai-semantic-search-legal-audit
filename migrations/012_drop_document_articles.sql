-- 012: Drop bang meta.document_articles (model DIEU KHOAN cu, truoc khi chuyen sang CAY).
--
-- Da duoc thay hoan toan bang meta.document_cay -> public.node/chunk. Bang nay 0 dong,
-- khong code nao dung. Cot document_relations.article_id (FK toi no) 100% NULL va khong
-- code nao doc -> drop luon, dung lai unique index khong con article_id (ngu nghia dedup
-- giu nguyen vi article_id luon NULL -> coalesce = 0).

-- DROP COLUMN tu dong go FK + unique index phu thuoc article_id.
ALTER TABLE meta.document_relations DROP COLUMN IF EXISTS article_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_relations
    ON meta.document_relations (vanban_tacdong_id, vanban_bitacdong_id, relation_type_id);

DROP TABLE IF EXISTS meta.document_articles;
DROP TYPE  IF EXISTS cap_dieukhoan;   -- enum chi document_articles su dung
