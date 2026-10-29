"""Sinh bao cao doi chieu dang Markdown, nhom theo 3 tag VI_PHAM/HOP_LE/CHUA_XAC_DINH."""
from __future__ import annotations

from psycopg import Connection

from app.db import repo_audit as ra

VI_PHAM_LOAI = {
    "dan_chieu_khong_ton_tai", "dan_chieu_sai_so_hieu",
    "dan_het_hieu_luc", "dan_bi_bai_bo", "dan_chua_hieu_luc",
    "trich_sai_nguyen_van", "the_thuc",
    "thu_hep_pham_vi", "mo_rong_pham_vi", "them_dieu_kien", "them_nghia_vu",
    "doi_so_lieu", "dat_thu_tuc_moi", "mau_thuan_truc_tiep", "vuot_tham_quyen",
}


def _tag(loai_loi: str) -> str:
    if loai_loi == "phu_hop":
        return "HOP_LE"
    if loai_loi == "khong_co_can_cu_uy_quyen":
        return "CHUA_XAC_DINH"
    if loai_loi in VI_PHAM_LOAI:
        return "VI_PHAM"
    return "HOP_LE"


def _ten_vb(cur, van_ban_id: str) -> str:
    if not van_ban_id:
        return ""
    cur.execute("SELECT so_hieu, ten FROM van_ban WHERE id=%s", (van_ban_id,))
    r = cur.fetchone()
    return f"{r[0]} - {r[1]}" if r else van_ban_id


def _vi_tri_don_vi(cur, don_vi_id: str) -> str:
    cur.execute(
        "SELECT so_dieu, so_khoan, diem, tieu_de, thu_tu FROM tai_lieu_don_vi WHERE id=%s",
        (don_vi_id,),
    )
    r = cur.fetchone()
    if not r:
        return don_vi_id
    sd, sk, dm, td, tt = r
    pos = ""
    if sd: pos += f"Dieu {sd}"
    if sk: pos += f" Khoan {sk}"
    if dm: pos += f" Diem {dm}"
    if not pos: pos = f"[Doan {tt}]"
    if td and sk is None and dm is None:
        pos += f" ({td})"
    return pos


def tao_report_md(conn: Connection, phien_id: str) -> str:
    ph = ra.lay_phien(conn, phien_id)
    if ph is None:
        return f"# Phien {phien_id} khong ton tai\n"
    lines: list[str] = []
    lines.append(f"# Bao cao doi chieu - phien {phien_id}")
    lines.append(f"- Tai lieu: {ph['tai_lieu_id']}")
    lines.append(f"- Ngay tra: {ph['ngay_tra']}")
    lines.append(f"- Thong ke: {ph['thong_ke']}")
    lines.append("")

    with conn.cursor() as cur:
        lines.append("## Van ban me")
        for vb in ra.danh_sach_van_ban_me(conn, phien_id):
            lines.append(f"- [{vb['duyet']}] {_ten_vb(cur, vb['van_ban_id'])} "
                         f"(nguon: {vb['nguon']})")
        lines.append("")

        ket_qua = ra.danh_sach_ket_qua(conn, phien_id)
        theo_tag: dict[str, list[dict]] = {"VI_PHAM": [], "CHUA_XAC_DINH": [], "HOP_LE": []}
        for k in ket_qua:
            theo_tag[_tag(k["loai_loi"])].append(k)

        tong = len(ket_qua)
        lines.append(f"## Tong hop: {tong} ket qua")
        lines.append(f"- **VI_PHAM**: {len(theo_tag['VI_PHAM'])}")
        lines.append(f"- **HOP_LE**: {len(theo_tag['HOP_LE'])}")
        lines.append(f"- **CHUA_XAC_DINH**: {len(theo_tag['CHUA_XAC_DINH'])}")
        lines.append("")

        for tag_name in ("VI_PHAM", "HOP_LE", "CHUA_XAC_DINH"):
            if not theo_tag[tag_name]:
                continue
            lines.append(f"## [{tag_name}]")
            for k in theo_tag[tag_name]:
                lines.append(f"### {_vi_tri_don_vi(cur, k['don_vi_id'])} "
                             f"- {k['loai_loi']} (tin_cay={k['tin_cay']:.2f})")
                if k.get("doan_du_thao"):
                    lines.append(f"**Du thao:**")
                    lines.append(f"> {k['doan_du_thao']}")
                if k.get("can_cu_van_ban_id") or k.get("can_cu_trich_dan"):
                    can_cu_vb = _ten_vb(cur, k.get("can_cu_van_ban_id") or "")
                    lines.append(f"**Can cu phap ly ({can_cu_vb}):**")
                    if k.get("can_cu_trich_dan"):
                        lines.append(f"> {k['can_cu_trich_dan']}")
                if k.get("giai_thich"):
                    lines.append(f"_{k['giai_thich']}_")
                if k.get("de_xuat_sua"):
                    lines.append(f"**De xuat sua:** {k['de_xuat_sua']}")
                lines.append("")
    return "\n".join(lines)
