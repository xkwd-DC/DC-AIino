"""M08 数据整备：清洗规则、县级匹配与接口合约。

覆盖
====
- 中文表头的自动映射与单位折算
- 重复县年、单位可疑、总产/单产矛盾的检出
- 中国模式：县名 → county_meta → county.db 气候回填
- 接口：上传 → 执行 → 导出 CSV/报告/脚本
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from api import ingest_api
from services import geo_climate, panel_cleaner


CSV_TEXT = """县名,年份,粮食产量(吨),播种面积(千公顷),单产(吨/公顷)
商水县,2018,550000,80.5,6.8
商水县,2019,560000,81.2,6.9
商水县,2020,545000,80.9,6.7
"""


def _upload(client, text: str = CSV_TEXT, name: str = "panel.csv"):
    data = {
        "mode": "china",
        "stats": (io.BytesIO(text.encode("utf-8")), name),
    }
    return client.post(
        "/api/ingest/sessions", data=data, content_type="multipart/form-data"
    )


def test_guess_mapping_chinese_headers():
    mapping = panel_cleaner.guess_mapping(
        ["县名", "年份", "粮食产量(吨)", "播种面积(千公顷)", "单产(吨/公顷)"]
    )
    assert mapping["region_name"]["column"] == "县名"
    assert mapping["year"]["column"] == "年份"
    assert mapping["grain_output_t"]["column"] == "粮食产量(吨)"
    assert mapping["sown_kha"]["column"] == "播种面积(千公顷)"
    assert mapping["yield_ton_per_ha"]["column"] == "单产(吨/公顷)"


def test_apply_mapping_converts_units():
    df = pd.DataFrame(
        {"县名": ["商水县"], "年份": [2019], "播种面积": [80500], "单产": [6800]}
    )
    mapping = {
        "region_name": {"column": "县名"},
        "year": {"column": "年份"},
        "sown_kha": {"column": "播种面积"},
        "yield_ton_per_ha": {"column": "单产"},
    }
    out = panel_cleaner.apply_mapping(
        df, mapping, {"sown_kha": "公顷", "yield_ton_per_ha": "公斤/公顷"}
    )
    assert out.loc[0, "sown_kha"] == pytest.approx(80.5)
    assert out.loc[0, "yield_ton_per_ha"] == pytest.approx(6.8)


def test_duplicate_region_year_is_blocker():
    clean = pd.DataFrame(
        {
            "region_code": [None, None],
            "region_name": ["商水县", "商水县"],
            "province": [None, None],
            "city": [None, None],
            "year": [2019, 2019],
            "grain_output_t": [1.0, 1.0],
            "sown_kha": [None, None],
            "yield_ton_per_ha": [None, None],
        }
    )
    findings = panel_cleaner.check_basic(clean)
    rules = {f["rule"] for f in findings}
    assert "duplicate_region_year" in rules
    assert any(f["level"] == "blocker" for f in findings if f["rule"] == "duplicate_region_year")


def test_parse_geojson_centroid(tmp_path):
    path = tmp_path / "units.geojson"
    path.write_text(
        """
        {"type":"FeatureCollection","features":[
          {"type":"Feature","properties":{"name":"UnitA"},
           "geometry":{"type":"Polygon","coordinates":[[[0,0],[2,0],[2,2],[0,2],[0,0]]]}}
        ]}
        """,
        encoding="utf-8",
    )
    units = geo_climate.parse_geojson(path)
    assert len(units) == 1
    assert units[0]["name"] == "UnitA"
    assert units[0]["lon"] == pytest.approx(1.0)
    assert units[0]["lat"] == pytest.approx(1.0)


def test_custom_mode_does_not_report_unmatched_when_all_matched():
    """国外模式的单元没有区划代码，match_method 才是判定依据。"""
    df = pd.DataFrame(
        {
            "region_name": ["A县", "B县"],
            "matched_code": [pd.NA, pd.NA],
            "matched_county": ["A县", "B县"],
            "match_method": ["geojson", "geojson"],
            "match_note": ["", ""],
        }
    )
    stats = {"total": 2, "matched": 2, "match_rate": 1.0}
    findings = panel_cleaner.check_regions(df, stats)
    assert not any(f["rule"] == "region_unmatched_sample" for f in findings)


def test_upload_run_export(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_api, "INGEST_DIR", tmp_path / "ingest")

    created = _upload(client)
    assert created.status_code == 200
    body = created.get_json()["data"]
    assert body["mode"] == "china"
    assert body["years"] == [2018, 2019, 2020]

    run = client.post(
        f"/api/ingest/sessions/{body['session_id']}/run",
        json={"mapping": body["mapping"], "units": body["units"]["chosen"]},
    )
    assert run.status_code == 200
    result = run.get_json()["data"]
    assert result["blocked"] is False
    assert result["summary"]["matched"] == 3
    assert result["summary"]["match_rate"] == 1.0
    # 商水县在县级面板里，2018-2020 都应有气候值
    assert result["summary"]["climate_covered"] == 3

    csv_resp = client.get(f"/api/ingest/sessions/{body['session_id']}/export/csv")
    assert csv_resp.status_code == 200
    assert "matched_code" in csv_resp.data.decode("utf-8-sig")

    report = client.get(f"/api/ingest/sessions/{body['session_id']}/export/report")
    assert report.status_code == 200
    assert "数据整备报告" in report.data.decode("utf-8")


def test_upload_rejects_bad_extension(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_api, "INGEST_DIR", tmp_path / "ingest")
    data = {"mode": "china", "stats": (io.BytesIO(b"x"), "a.exe")}
    resp = client.post(
        "/api/ingest/sessions", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 400


def test_custom_mode_requires_geo(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_api, "INGEST_DIR", tmp_path / "ingest")
    data = {"mode": "custom", "stats": (io.BytesIO(CSV_TEXT.encode()), "a.csv")}
    resp = client.post(
        "/api/ingest/sessions", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert "地理文件" in resp.get_json()["error"]["message"]
