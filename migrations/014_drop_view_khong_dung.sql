-- 014: Drop 5 view khong co code nao dung (chi tien tay soi DB thu cong).
-- Deu nam o schema vanban sau reorg 013. Can lai thi lay dinh nghia tu 002/003/006.
DROP VIEW IF EXISTS vanban.v_documents;
DROP VIEW IF EXISTS vanban.v_document_relations;
DROP VIEW IF EXISTS vanban.v_dieu;
DROP VIEW IF EXISTS vanban.v_khoan;
DROP VIEW IF EXISTS vanban.v_node_chunk;
