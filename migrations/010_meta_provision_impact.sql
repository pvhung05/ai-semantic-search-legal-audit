-- 010: Luu tac dong CAP DIEU KHOAN (provision-level) do service crawl ghi vao meta.
--
-- Nguon: trang GET chi-tiet (thuoc tinh `type="<ma>:<source_provision_id>"` tren moi <p>)
-- + Server Action 2836b800 (chi tiet tung diem: sourceProvisions[] / targetProvision).
--
-- Hat = 1 CANH tac dong (target_provision <- source_provision): 1 diem co the bi nhieu
-- lenh (sourceProvisions la mang) nen moi cap la 1 dong. Khong cascade khi luu: luu dung
-- node bi danh dau (Dieu HOAC Khoan); suy ra anh huong cap duoi lam o query path-based ben public.
--
-- Lam moi: service crawl DELETE theo target_doc_id roi INSERT lai (giong save_relations).

CREATE TABLE IF NOT EXISTS meta.provision_impacts (
    id                   bigserial PRIMARY KEY,
    target_doc_id        text NOT NULL REFERENCES meta.documents(id) ON DELETE CASCADE,
    target_provision_id  text    NOT NULL,                 -- <p id> = public.node.id (cap Dieu/Khoan/Diem tra qua node.cap)
    target_order_index   int,
    source_doc_id        text REFERENCES meta.documents(id),-- VB thuc hien tac dong (co the la stub)
    source_provision_id  text,
    source_title         text,                              -- "Khoan 4, Dieu 49" + titleDocument
    relation_type_id     int  NOT NULL REFERENCES meta.relation_types(id),
    eff_from             date,
    eff_to               date,
    content              text,                              -- noi dung lenh (sourceProvision.content)
    raw                  jsonb,                             -- full payload, phong khi doi mapping khoi crawl lai
    crawled_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (target_provision_id, source_provision_id, relation_type_id, eff_from)
);

CREATE INDEX IF NOT EXISTS prov_impact_target ON meta.provision_impacts (target_doc_id);
CREATE INDEX IF NOT EXISTS prov_impact_source ON meta.provision_impacts (source_doc_id);
