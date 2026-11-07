-- 006: View tien xem text_goc/text_embed cua chunk canh metadata node
-- (cap, tieu_de, noi_dung, is_leaf). Chi doc, khong doi du lieu.
CREATE OR REPLACE VIEW v_node_chunk AS
SELECT
  n.id          AS node_id,
  n.van_ban_id,
  n.cap,
  n.duong_dan,
  n.tieu_de,
  n.noi_dung,
  n.is_leaf,
  c.id          AS chunk_id,
  c.text_goc,
  c.text_embed
FROM public.node n
JOIN public.chunk c ON c.node_id = n.id
ORDER BY n.van_ban_id, n.order_index;
