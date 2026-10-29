"""Test summarize voi LLM mock."""
from app.ingestion.summarize import _tom_tat_fallback, tom_tat_dieu
from app.models.schemas import Dieu


def _dieu(so: str, tieu_de: str, noi_dung: str) -> Dieu:
    return Dieu(so_dieu=so, so_dieu_num=int(so), tieu_de=tieu_de,
                noi_dung=noi_dung, thu_tu=int(so))


def test_fallback_khi_khong_co_llm():
    d = _dieu("1", "Pham vi", "Thong tu nay quy dinh ve ...")
    tom = _tom_tat_fallback(d)
    assert tom.startswith("Pham vi")


def test_batch_voi_mock_tra_tom_tat():
    data = [_dieu(str(i), f"Dieu {i}", f"Noi dung {i}") for i in range(1, 6)]

    def mock(messages):
        return [{"dieu_id": d.so_dieu, "tom_tat": f"tom tat {d.so_dieu}"} for d in data]

    out = tom_tat_dieu(data, batch_size=5, goi_json_fn=mock)
    assert all(d.tom_tat and d.tom_tat.startswith("tom tat") for d in out)


def test_batch_loi_llm_fallback():
    data = [_dieu("1", "T1", "nd1"), _dieu("2", "T2", "nd2")]

    def mock_loi(messages):
        raise RuntimeError("mock loi")

    out = tom_tat_dieu(data, batch_size=5, goi_json_fn=mock_loi)
    assert all(d.tom_tat for d in out)
    assert out[0].tom_tat.startswith("T1")
