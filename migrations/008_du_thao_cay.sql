-- 008: Kho DU THAO (van ban dang soan) de doi sanh voi kho luat. Doi xung van_ban -> node/chunk.
--  du_thao       = thong tin van ban + cay da segment (JSON goc). User chi upload file,
--                  khong nhap metadata -> chi id, toan van, cay JSON, created_at.
--  du_thao_node  = kho chunk: moi don vi 1 dong, co text_embed + embedding vector(1024).
-- `cap` dung text (khong dung enum cap_node) vi segment du thao con cap 'doan'/'cum'.
BEGIN;

CREATE TABLE IF NOT EXISTS du_thao (
  id          text PRIMARY KEY,
  noi_dung    text,                                   -- toan van tho doc tu file
  cay         jsonb NOT NULL DEFAULT '{}',            -- KetQuaSegment: {don_vi, can_cu_tho, co_cau_truc_dieu}
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS du_thao_node (
  id           text PRIMARY KEY,                                      -- id don vi segment
  du_thao_id   text NOT NULL REFERENCES du_thao(id) ON DELETE CASCADE,
  parent_id    text REFERENCES du_thao_node(id) ON DELETE CASCADE,   -- Diem -> Khoan me
  cap          text NOT NULL,                                        -- dieu|khoan|diem|doan|cum
  so_dieu      text,
  so_khoan     text,
  diem         text,
  tieu_de      text,
  noi_dung     text,                                                 -- text_goc (nguyen van don vi)
  thu_tu       int NOT NULL DEFAULT 0,
  text_embed   text,                                                 -- text dua di embed (tieu_de + noi_dung)
  embedding    vector(1024)
);
CREATE INDEX IF NOT EXISTS du_thao_node_vb     ON du_thao_node (du_thao_id, thu_tu);
CREATE INDEX IF NOT EXISTS du_thao_node_parent ON du_thao_node (parent_id);

COMMIT;
