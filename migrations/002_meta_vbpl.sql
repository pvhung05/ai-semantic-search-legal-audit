-- Schema `meta` trong database `luatvn`: kho du lieu van ban QPPL
-- Nguon: vbpl.vn (Next.js App Router + Server Actions).
--
-- Metadata duoc trich tu 4 API JSON chi tiet:
--   doc_info  (0fb12b35) : thong tin van ban (docType, organization, issues, majors, fields, files...)
--   luoc_do   (4a3423ce) : quan he 2 chieu (byType / bySource)
--   lich_su   (fe4862cb) : lifecycle (ban hanh, hieu luc) + ngay tac dong hieu luc
--   vbhn      (0932c380) : van ban hop nhat
-- va 1 API noi dung: toan_van (233848b4) : HTML toan van.

CREATE SCHEMA IF NOT EXISTS meta;
SET search_path TO meta, public;

-- ---------- 1. BANG DANH MUC ----------
-- vbpl_id: id goc tren vbpl.vn (de mapping on dinh); ma: code nghiep vu (co the null -> dung vbpl_id).

CREATE TABLE IF NOT EXISTS loai_vanban (
    id       SERIAL PRIMARY KEY,
    vbpl_id  VARCHAR(50) UNIQUE,
    ma       VARCHAR(40)  NOT NULL UNIQUE,     -- docType.code: 'TT','ND','LUAT'
    ten      VARCHAR(150) NOT NULL,
    nhom     VARCHAR(40),                       -- docType.parentCode: 'VBQPPL'
    mo_ta    TEXT
);

CREATE TABLE IF NOT EXISTS coquan_banhanh (
    id       SERIAL PRIMARY KEY,
    vbpl_id  VARCHAR(50) UNIQUE,
    ma       VARCHAR(50)  NOT NULL UNIQUE,     -- organization.code: 'BTC','CP','QH'
    ten      VARCHAR(255) NOT NULL,
    ten_en   VARCHAR(255),
    mo_ta    TEXT
);

CREATE TABLE IF NOT EXISTS nganh (
    id       SERIAL PRIMARY KEY,
    vbpl_id  VARCHAR(50) UNIQUE,               -- documentMajors.id: 'nganh_63'
    ma       VARCHAR(50)  NOT NULL UNIQUE,
    ten      VARCHAR(255) NOT NULL,
    mo_ta    TEXT
);

CREATE TABLE IF NOT EXISTS linhvuc (
    id       SERIAL PRIMARY KEY,
    vbpl_id  VARCHAR(50) UNIQUE,               -- documentFields.id: '7252'
    ma       VARCHAR(50)  NOT NULL UNIQUE,
    ten      VARCHAR(255) NOT NULL,
    mo_ta    TEXT
);

CREATE TABLE IF NOT EXISTS chucdanh (
    id       SERIAL PRIMARY KEY,
    vbpl_id  VARCHAR(50) UNIQUE,               -- documentIssues.jobTitleId
    ma       VARCHAR(50)  NOT NULL UNIQUE,     -- jobTitleCode: 'TT3'
    ten      VARCHAR(100) NOT NULL,
    mo_ta    TEXT
);

CREATE TABLE IF NOT EXISTS relation_types (
    id               SERIAL PRIMARY KEY,
    vbpl_code        VARCHAR(10) UNIQUE,        -- ma so vbpl: '3','4','9','10','12','1','7'
    ma               VARCHAR(40)  NOT NULL UNIQUE,
    ten_chieu_thuan  VARCHAR(255) NOT NULL,
    ten_chieu_nguoc  VARCHAR(255) NOT NULL,
    mo_ta            TEXT
);

-- ---------- 2. VAN BAN ----------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'trangthai_hieuluc') THEN
        CREATE TYPE trangthai_hieuluc AS ENUM (
            'CHUA_HIEU_LUC', 'CON_HIEU_LUC', 'HET_HIEU_LUC_MOT_PHAN',
            'HET_HIEU_LUC', 'TAM_NGUNG', 'KHONG_XAC_DINH'
        );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS documents (
    id               TEXT PRIMARY KEY,                 -- id tu vbpl.vn (uuid hoac so chuoi)
    so_hieu          VARCHAR(150),                     -- docNum
    tieu_de          TEXT         NOT NULL,            -- title
    loai_vanban_id   INT          REFERENCES loai_vanban(id),
    coquan_id        INT          REFERENCES coquan_banhanh(id),   -- organization chinh
    nganh_id         INT          REFERENCES nganh(id),            -- nganh dau tien (tien loi)
    chucdanh_id      INT          REFERENCES chucdanh(id),         -- chuc danh nguoi ky dau tien
    nguoi_ky         VARCHAR(255),                     -- documentIssues[0].personName
    docgroup         VARCHAR(40),                      -- docGroup: 'VBQPPL'
    ngay_banhanh     DATE,                             -- issueDate
    ngay_hieuluc     DATE,                             -- effFrom
    ngay_hethieuluc  DATE,                             -- effTo
    ngay_congbo      DATE,                             -- publicDate
    trangthai        trangthai_hieuluc NOT NULL DEFAULT 'KHONG_XAC_DINH',
    effstatus_code   VARCHAR(20),                      -- effStatus.code: 'HHL','CHL',...
    ghi_chu_apdung   TEXT,                             -- applicationNote
    lang             VARCHAR(10),
    is_consolidated  BOOLEAN NOT NULL DEFAULT false,   -- isConsolidatedDocument
    vbpl_updated_date TIMESTAMPTZ,                     -- updatedDate
    nguon_url        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_sohieu       ON documents(so_hieu);
CREATE INDEX IF NOT EXISTS idx_documents_coquan       ON documents(coquan_id);
CREATE INDEX IF NOT EXISTS idx_documents_loai         ON documents(loai_vanban_id);
CREATE INDEX IF NOT EXISTS idx_documents_ngaybanhanh  ON documents(ngay_banhanh DESC);
CREATE INDEX IF NOT EXISTS idx_documents_trangthai    ON documents(trangthai);

-- Van ban thuoc nhieu NGANH (documentMajors)
CREATE TABLE IF NOT EXISTS document_nganh (
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    nganh_id     INT  NOT NULL REFERENCES nganh(id),
    PRIMARY KEY (document_id, nganh_id)
);
CREATE INDEX IF NOT EXISTS idx_document_nganh_n ON document_nganh(nganh_id);

-- Van ban thuoc nhieu LINH VUC (documentFields)
CREATE TABLE IF NOT EXISTS document_linhvuc (
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    linhvuc_id   INT  NOT NULL REFERENCES linhvuc(id),
    PRIMARY KEY (document_id, linhvuc_id)
);
CREATE INDEX IF NOT EXISTS idx_document_linhvuc_lv ON document_linhvuc(linhvuc_id);

-- Nguoi ky / co quan ky (documentIssues) - co the nhieu dong (lien tich)
CREATE TABLE IF NOT EXISTS document_issues (
    id           BIGSERIAL PRIMARY KEY,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    coquan_id    INT  REFERENCES coquan_banhanh(id),
    chucdanh_id  INT  REFERENCES chucdanh(id),
    nguoi_ky     VARCHAR(255),
    thu_tu       INT,                           -- orderIndex
    UNIQUE (document_id, coquan_id, nguoi_ky, chucdanh_id)
);
CREATE INDEX IF NOT EXISTS idx_document_issues_doc ON document_issues(document_id);

-- Toan van (1-1 voi documents)
CREATE TABLE IF NOT EXISTS document_content (
    document_id   TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    noidung       TEXT,
    noidung_html  TEXT,
    file_path     TEXT,
    version       INT NOT NULL DEFAULT 1,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    tsv           tsvector GENERATED ALWAYS AS
                  (to_tsvector('simple', coalesce(noidung, ''))) STORED
);
CREATE INDEX IF NOT EXISTS idx_document_content_tsv ON document_content USING GIN (tsv);

-- Cau truc Chuong/Muc/Dieu/Khoan/Diem (tuy chon, chua dung o vong nay)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cap_dieukhoan') THEN
        CREATE TYPE cap_dieukhoan AS ENUM ('PHAN','CHUONG','MUC','DIEU','KHOAN','DIEM');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS document_articles (
    id              BIGSERIAL PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    parent_id       BIGINT REFERENCES document_articles(id) ON DELETE CASCADE,
    cap             cap_dieukhoan NOT NULL,
    so_thutu        VARCHAR(20),
    tieu_de         TEXT,
    noidung         TEXT,
    thu_tu_hienthi  INT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_doc    ON document_articles(document_id, thu_tu_hienthi);
CREATE INDEX IF NOT EXISTS idx_articles_parent ON document_articles(parent_id);

-- ---------- 3. QUAN HE GIUA CAC VAN BAN ----------

CREATE TABLE IF NOT EXISTS document_relations (
    id                  BIGSERIAL PRIMARY KEY,
    vanban_tacdong_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    vanban_bitacdong_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relation_type_id    INT  NOT NULL REFERENCES relation_types(id),
    article_id          BIGINT REFERENCES document_articles(id) ON DELETE SET NULL,
    effect_all_type     SMALLINT,              -- effectAllType: 0=1 phan, 1=toan bo, null
    ghi_chu             TEXT,
    ngay_hieuluc        DATE,                  -- effFrom tu lich_su
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_relation_khong_tu_tro CHECK (vanban_tacdong_id <> vanban_bitacdong_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_relations
    ON document_relations (vanban_tacdong_id, vanban_bitacdong_id, relation_type_id,
                           coalesce(article_id, 0));

CREATE INDEX IF NOT EXISTS idx_relations_tacdong   ON document_relations(vanban_tacdong_id);
CREATE INDEX IF NOT EXISTS idx_relations_bitacdong ON document_relations(vanban_bitacdong_id);
CREATE INDEX IF NOT EXISTS idx_relations_type      ON document_relations(relation_type_id);

-- Van ban hop nhat (vbhn): nhom hop nhat + thanh phan
CREATE TABLE IF NOT EXISTS vbhn_nhom (
    vbhn_id      TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,  -- vbhnDocument.id
    thanhvien_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,  -- mergedDocuments[].id
    la_hien_tai  BOOLEAN NOT NULL DEFAULT false,                             -- current
    PRIMARY KEY (vbhn_id, thanhvien_id)
);
CREATE INDEX IF NOT EXISTS idx_vbhn_thanhvien ON vbhn_nhom(thanhvien_id);

-- ---------- 4. BANG QUAN LY CRAWL ----------

CREATE TABLE IF NOT EXISTS crawl_queue (
    id_ref          TEXT PRIMARY KEY,
    slug            TEXT,
    trang_thai      VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    so_lan_thu      INT NOT NULL DEFAULT 0,
    loi             TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    cap_nhat        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_crawl_queue_status ON crawl_queue(trang_thai, so_lan_thu);

CREATE TABLE IF NOT EXISTS raw_html (
    id_ref       TEXT NOT NULL,
    loai_trang   VARCHAR(50) NOT NULL,
    html         BYTEA,
    http_status  INT,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id_ref, loai_trang)
);

CREATE TABLE IF NOT EXISTS action_config (
    ten        VARCHAR(50) PRIMARY KEY,
    action_id  VARCHAR(100) NOT NULL,
    body_mau   JSONB,
    ghi_chu    TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- 5. TRIGGER updated_at ----------

CREATE OR REPLACE FUNCTION meta.set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION meta.set_updated_at();

DROP TRIGGER IF EXISTS trg_document_content_updated_at ON document_content;
CREATE TRIGGER trg_document_content_updated_at
    BEFORE UPDATE ON document_content
    FOR EACH ROW EXECUTE FUNCTION meta.set_updated_at();

-- ---------- 6. DU LIEU MAU DANH MUC QUAN HE ----------
-- vbpl_code anh xa key so trong luoc_do (documentNamesByType/BySource).

INSERT INTO relation_types (vbpl_code, ma, ten_chieu_thuan, ten_chieu_nguoc) VALUES
('3',  'CAN_CU_BAN_HANH',   'Văn bản được dùng làm căn cứ',                 'Căn cứ ban hành'),
('4',  'DAN_CHIEU',         'Văn bản dẫn chiếu',                            'Văn bản được dẫn chiếu'),
('9',  'HUONG_DAN_AP_DUNG', 'Văn bản hướng dẫn, quy định chi tiết',         'Văn bản được hướng dẫn, quy định chi tiết'),
('10', 'SUA_DOI_BO_SUNG',   'Văn bản sửa đổi, bổ sung',                     'Văn bản bị sửa đổi, bổ sung'),
('12', 'THAY_THE',          'Văn bản thay thế',                             'Văn bản bị thay thế'),
('1',  'BAI_BO',            'Văn bản bãi bỏ',                               'Văn bản bị bãi bỏ'),
('7',  'HOP_NHAT',          'Văn bản hợp nhất',                             'Văn bản được hợp nhất')
ON CONFLICT (ma) DO UPDATE SET
    vbpl_code = EXCLUDED.vbpl_code,
    ten_chieu_thuan = EXCLUDED.ten_chieu_thuan,
    ten_chieu_nguoc = EXCLUDED.ten_chieu_nguoc;

-- Loai quan he khac (chi dung o lich_su / phan loai noi bo), khong co vbpl_code:
INSERT INTO relation_types (ma, ten_chieu_thuan, ten_chieu_nguoc) VALUES
('HET_HL_MOT_PHAN', 'Văn bản làm hết hiệu lực một phần', 'Văn bản bị hết hiệu lực một phần'),
('HET_HL_TOAN_BO',  'Văn bản làm hết hiệu lực toàn bộ',  'Văn bản bị hết hiệu lực toàn bộ'),
('DINH_CHINH',      'Văn bản đính chính',                'Văn bản được đính chính'),
('DINH_CHI_THI_HANH','Văn bản đình chỉ thi hành',        'Văn bản bị đình chỉ thi hành'),
('TAM_NGUNG_GIA_HAN','Văn bản tạm ngưng/gia hạn hiệu lực','Văn bản bị tạm ngưng/gia hạn hiệu lực')
ON CONFLICT (ma) DO NOTHING;

-- ---------- 7. VIEW: tra quan he hai chieu cho mot van ban ----------

CREATE OR REPLACE VIEW v_document_relations AS
SELECT r.id,
       r.vanban_tacdong_id   AS document_id,
       r.vanban_bitacdong_id AS vanban_lienquan_id,
       t.ma                  AS relation_ma,
       t.ten_chieu_thuan     AS ten_quan_he,
       r.effect_all_type, r.ghi_chu, r.ngay_hieuluc
FROM document_relations r JOIN relation_types t ON t.id = r.relation_type_id
UNION ALL
SELECT r.id,
       r.vanban_bitacdong_id,
       r.vanban_tacdong_id,
       t.ma,
       t.ten_chieu_nguoc,
       r.effect_all_type, r.ghi_chu, r.ngay_hieuluc
FROM document_relations r JOIN relation_types t ON t.id = r.relation_type_id;

-- ---------- 8. DU LIEU MAC DINH ----------

INSERT INTO loai_vanban(ma, ten) VALUES ('KXD', 'Không xác định')
    ON CONFLICT (ma) DO NOTHING;
INSERT INTO coquan_banhanh(ma, ten) VALUES ('KXD', 'Không xác định')
    ON CONFLICT (ma) DO NOTHING;
