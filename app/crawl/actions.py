"""Server Action IDs mac dinh (sniff ngay 2026-10-30).

Khi vbpl.vn deploy lai, action ID se doi. Luu truoc vao vanban.action_config
qua seed_actions(); crawler doc config truoc moi POST, neu loi 400/404
thi can sniff lai.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    ten: str
    action_id: str
    body_mau: str
    ghi_chu: str


DEFAULT_ACTIONS: tuple[Action, ...] = (
    Action(
        ten="list",
        action_id="c529d164f28418e5898a834422629e64c6816af1",
        body_mau=(
            '[{"pageNumber":1,"pageSize":100,"keyword":"$undefined",'
            '"sortBy":"issueDate","sortDirection":"desc","groupVbpl":false,'
            '"documentName":"$undefined","docNum":"$undefined","docType":"$undefined",'
            '"majorTypeIds":"$undefined","fieldTypeIds":"$undefined",'
            '"agencyIds":"$undefined","effStatus":"$undefined","status":"$undefined",'
            '"agencyLevel":"TRUNG_UONG","administrativeUnit":"$undefined",'
            '"documentType":"$undefined","optionDoc":"all","matchMode":"all_words"}]'
        ),
        ghi_chu="Danh sach van ban TW; agencyLevel=TRUNG_UONG; total ~57k",
    ),
    Action(
        ten="lien_quan",
        action_id="4a3423ce75290ef83a022333ee187acf4d38d3fb",
        body_mau='["66801"]',
        ghi_chu=("Luoc do FULL 2 chieu: documentNamesByType (A->B: can cu, huong dan, sua doi...) "
                 "va documentNamesBySource (B->A: bi sua doi, VBHN, bi bai bo...)"),
    ),
    Action(
        ten="luoc_do",
        action_id="fe4862cb550ced8ac0057edfdf498bca2229be52",
        body_mau='["66801"]',
        ghi_chu="Tac dong hieu luc (co nhan Viet status + effFrom) + lifecycle cua A",
    ),
    Action(
        ten="vbhn",
        action_id="0932c3801e9e99306fe7e694562e44ba55134662",
        body_mau='["66801"]',
        ghi_chu="Thong tin Van ban hop nhat (vbhnDocument va mergedDocuments)",
    ),
    Action(
        ten="danh_muc",
        action_id="d6528df4e9bac9985453396c8dd8ba9f66475cec",
        body_mau='[{"groupCode":"LoaiVanBan","keyword":"$undefined","includeInactive":true}]',
        ghi_chu="Danh muc chung (LoaiVanBan, TrangThaiHieuLuc, LinhVuc)",
    ),
    Action(
        ten="co_quan",
        action_id="783db08bc37c256b4b72e2678699d7b96852270f",
        body_mau='[{"keyword":"$undefined","type":"TW","administrativeUnitId":"$undefined","includeInactive":true}]',
        ghi_chu="Danh muc co quan ban hanh TW",
    ),
    Action(
        ten="toc",
        action_id="94635012466e8fede44782d4237c10fe75501920",
        body_mau='["66801"]',
        ghi_chu="Cay Chuong/Dieu/Khoan cua mot van ban (tab 'Noi dung')",
    ),
    Action(
        ten="document_html",
        action_id="0fb12b3561faa05adec51a82efb3e4f4f427f07b",
        body_mau='["66801"]',
        ghi_chu="HTML toan van cua mot van ban bat ky",
    ),
)
