-- 009: Cap nhat day du bang meta.relation_types theo enum chinh thuc cua vbpl.vn
-- (trich tu JS cua site ngay 2026-11-04: 18 ma loai quan he/tac dong).
--
-- Luu y:
--  * Day la cung he ma dung trong luoc_do (documentNamesByType/BySource) va trong
--    thuoc tinh `type` cap dieu khoan tren trang chi-tiet.
--  * Seed cu (002) gan nham ma 9 = "Huong dan ap dung". Enum chinh thuc:
--      8 = Huong dan ap dung ; 9 = Quy dinh chi tiet, huong dan thi hanh.
--  * document_relations duoc dung lai moi lan crawl (DELETE + INSERT, tra id theo
--    vbpl_code) nen viec gan lai ma khong lam hong du lieu; se tu dong dung theo
--    mapping moi o lan crawl ke tiep.

-- 1) Go het vbpl_code cu de tranh va cham rang buoc UNIQUE khi gan lai.
UPDATE meta.relation_types SET vbpl_code = NULL WHERE vbpl_code IS NOT NULL;

-- 2) UPSERT 18 ma chuan (theo `ma`), tai su dung slug da co khi trung.
INSERT INTO meta.relation_types (vbpl_code, ma, ten_chieu_thuan, ten_chieu_nguoc) VALUES
('1',  'BAI_BO',                'Văn bản bãi bỏ',                                  'Văn bản bị bãi bỏ'),
('2',  'BAN_DICH',              'Bản dịch của văn bản',                            'Văn bản được dịch'),
('3',  'CAN_CU_BAN_HANH',       'Văn bản được dùng làm căn cứ',                    'Căn cứ ban hành'),
('4',  'DAN_CHIEU',             'Văn bản dẫn chiếu',                               'Văn bản được dẫn chiếu'),
('5',  'DINH_CHI_THI_HANH',     'Văn bản đình chỉ thi hành',                       'Văn bản bị đình chỉ thi hành'),
('6',  'DINH_CHINH',            'Văn bản đính chính',                              'Văn bản được đính chính'),
('7',  'HOP_NHAT',              'Văn bản hợp nhất',                                'Văn bản được hợp nhất'),
('8',  'HUONG_DAN_AP_DUNG',     'Văn bản hướng dẫn áp dụng',                       'Văn bản được hướng dẫn áp dụng'),
('9',  'QUY_DINH_CHI_TIET',     'Văn bản quy định chi tiết, hướng dẫn thi hành',   'Văn bản được quy định chi tiết, hướng dẫn thi hành'),
('10', 'SUA_DOI_BO_SUNG',       'Văn bản sửa đổi, bổ sung',                        'Văn bản bị sửa đổi, bổ sung'),
('11', 'TAM_NGUNG_HIEU_LUC',    'Văn bản làm tạm ngưng hiệu lực',                  'Văn bản bị tạm ngưng hiệu lực'),
('12', 'THAY_THE',              'Văn bản thay thế',                                'Văn bản bị thay thế'),
('13', 'BO_SUNG',               'Văn bản bổ sung',                                 'Văn bản bị bổ sung'),
('14', 'GIAI_THICH',            'Văn bản giải thích',                              'Văn bản được giải thích'),
('15', 'CONG_BO',               'Văn bản công bố',                                 'Văn bản được công bố'),
('16', 'SUA_DOI',               'Văn bản sửa đổi',                                 'Văn bản bị sửa đổi'),
('17', 'GIA_HAN_HIEU_LUC',      'Văn bản gia hạn hiệu lực',                        'Văn bản được gia hạn hiệu lực'),
('18', 'TIEP_TUC_CON_HIEU_LUC', 'Văn bản xác nhận tiếp tục còn hiệu lực',          'Văn bản được xác nhận tiếp tục còn hiệu lực')
ON CONFLICT (ma) DO UPDATE SET
    vbpl_code       = EXCLUDED.vbpl_code,
    ten_chieu_thuan = EXCLUDED.ten_chieu_thuan,
    ten_chieu_nguoc = EXCLUDED.ten_chieu_nguoc;
