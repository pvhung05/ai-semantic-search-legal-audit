from __future__ import annotations

import tasks


def test_broken_links_bao_link_hong_bo_qua_url_anchor_va_code_fence(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    (tmp_path / "co.md").write_text("x", encoding="utf-8")
    md = tmp_path / "doc.md"
    text = "\n".join([
        "[ok](co.md) [ok anchor](co.md#muc) [hong](khong_co.md)",
        "[web](https://example.com) [neo](#tieu-de)",
        "```",
        "[trong fence](cung_khong_co.md)",
        "```",
    ])
    assert tasks.broken_links(md, text) == ["doc.md:1 -> khong_co.md"]


def test_stale_docs_canh_bao_khi_code_doi_ma_tai_lieu_module_khong_doi():
    doc_dirs = {"app/core", "app/doisanh", "app/doisanh/audit"}
    changed = {"app/core/config.py", "app/doisanh/audit/so_sanh.py", "README.md", "tasks.py"}
    assert tasks.stale_docs(changed, doc_dirs) == {
        "app/core": ["app/core/config.py"],
        "app/doisanh/audit": ["app/doisanh/audit/so_sanh.py"],
    }


def test_stale_docs_tai_lieu_module_cha_doi_thi_khong_canh_bao():
    doc_dirs = {"app/doisanh", "app/doisanh/audit"}
    changed = {"app/doisanh/audit/so_sanh.py", "app/doisanh/ARCHITECTURE.md"}
    assert tasks.stale_docs(changed, doc_dirs) == {}
