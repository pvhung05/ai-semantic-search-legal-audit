-- 011: public.tac_dong giu du fidelity (18 ma) + tra tac dong theo CA DUONG CAY.
--
-- tac_dong (003) chi co enum `loai` hep (7 gia tri). Them relation_type_id de khong mat
-- 18 ma vbpl, + eff_den/order_index. Index duong_dan cho tra prefix nhanh.
--
-- Ham impacts_cho_node: tra impact nam tren CHINH node, TO TIEN, hoac CON CHAU cua no.
-- Giai quyet: "Dieu K bi thay the, du thao chi nhac khoan e thuoc K" -> van bat duoc.

ALTER TABLE tac_dong ADD COLUMN IF NOT EXISTS relation_type_id int REFERENCES meta.relation_types(id);
ALTER TABLE tac_dong ADD COLUMN IF NOT EXISTS hieu_luc_den date;
ALTER TABLE tac_dong ADD COLUMN IF NOT EXISTS order_index  int;

CREATE INDEX IF NOT EXISTS node_duongdan ON node (van_ban_id, duong_dan text_pattern_ops);

CREATE OR REPLACE FUNCTION impacts_cho_node(p_node_id text)
RETURNS SETOF tac_dong
LANGUAGE sql STABLE AS $$
    WITH ref AS (SELECT van_ban_id, duong_dan FROM node WHERE id = p_node_id)
    SELECT td.*
    FROM tac_dong td
    JOIN node nd ON nd.id = td.node_dich_id
    JOIN ref    ON nd.van_ban_id = ref.van_ban_id
    WHERE ref.duong_dan = nd.duong_dan                 -- chinh no
       OR ref.duong_dan LIKE nd.duong_dan || '>%'      -- impact o TO TIEN (bien theo '>')
       OR nd.duong_dan  LIKE ref.duong_dan || '>%';    -- impact o CON CHAU
$$;
