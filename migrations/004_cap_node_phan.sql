-- =====================================================================
-- 004: Bo sung cap 'phan' (Phan) vao enum cap_node.
--
-- API vbpl co level 'Part' cao hon 'Chapter' (thuong gap o Bo luat):
--   Part (Phan) > Chapter (Chuong) > Section (Muc) > Article (Dieu)
--     > Clause (Khoan) > Point (Diem).
-- Khong sua migration 003 da ap dung; chi them gia tri enum (PG16).
-- =====================================================================

BEGIN;

ALTER TYPE cap_node ADD VALUE IF NOT EXISTS 'phan' BEFORE 'chuong';

COMMIT;
