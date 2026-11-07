-- 015: View soi tac dong gon: so hieu 2 van ban + diem dich/nguon + noi dung bi doi & lenh doi.
DROP VIEW IF EXISTS vanban.v_tac_dong;
CREATE VIEW vanban.v_tac_dong AS
SELECT vn.so_hieu       AS so_hieu_nguon,     -- van ban di tac dong
       vd.so_hieu       AS so_hieu_dich,      -- van ban bi tac dong
       nd.duong_dan     AS diem_dich,         -- diem bi thay doi (vd CI>D8>K8)
       td.nguon_lenh    AS diem_nguon,        -- diem thuc hien lenh (vd "Khoan 4, Dieu 49")
       nd.noi_dung      AS noi_dung_diem_dich,-- noi dung diem bi thay doi
       td.noi_dung_moi  AS noi_dung_thay_doi  -- noi dung lenh thay doi
FROM vanban.tac_dong td
JOIN vanban.node nd          ON nd.id = td.node_dich_id
JOIN vanban.van_ban vd       ON vd.id = nd.van_ban_id
LEFT JOIN vanban.van_ban vn  ON vn.id = td.van_ban_nguon_id;
