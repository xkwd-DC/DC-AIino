"""县级面板端点合约测试（M07）。

覆盖 services.county_repo + api.county_api 的读路径与错误码：
200 正常取数 / 400 参数错 / 404 县不存在 / 503 数据层缺失。

策略
====
1. inline schema + 极少量 dummy 行（2 县 × 2 年），只验合约不验数据完整性；
2. monkeypatch `county_repo.DEFAULT_DB_PATH` 指向 tmp_path 的临时库；
3. AAA 结构，对齐 backend/tests/test_panel_endpoints.py 风格。
"""

from __future__ import annotations

import sqlite3

import pytest

from services import county_repo

# 归因接口会 SELECT 全部 16 个 shap_* 列，测试库按 repo 的特征字典生成，
# 保证 schema 与真实 county.db 同形（口径只有一处定义）。
_TEST_FEATURES = list(county_repo.FEATURE_DICT)
_SHAP_COLS = ",\n    ".join(f"shap_{f} REAL" for f in _TEST_FEATURES)
_CLIM_COLS = ",\n    ".join(f"{f} REAL" for f in _TEST_FEATURES)

SCHEMA = f"""
CREATE TABLE county_meta (
    county_code INTEGER PRIMARY KEY, province TEXT, city TEXT, county TEXT,
    lon REAL, lat REAL, map_key TEXT, on_map INTEGER
);
CREATE TABLE county_panel (
    county_code INTEGER, year INTEGER, grain_output_t REAL, sown_kha REAL,
    log_yield REAL, yield_ton_per_ha REAL,
    {_CLIM_COLS},
    PRIMARY KEY (county_code, year)
);
CREATE TABLE county_model_out (
    county_code INTEGER, year INTEGER, y_true REAL, y_pred REAL,
    clim_contrib REAL, clim_anomaly REAL, risk_level INTEGER, risk_pct REAL,
    contrib_pct REAL, unit_type TEXT,
    {_SHAP_COLS},
    PRIMARY KEY (county_code, year)
);
CREATE TABLE feature_direction (
    feature TEXT PRIMARY KEY, train_shap REAL, test_shap REAL, same_sign INTEGER
);
CREATE TABLE county_standard (group_name TEXT, item TEXT, value TEXT);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
"""


@pytest.fixture()
def county_db(tmp_path, monkeypatch):
    db = tmp_path / "county.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO county_meta VALUES (?,?,?,?,?,?,?,?)",
        [
            (110108, "北京市", "北京市", "海淀区", 116.3, 39.9, "海淀区", 1),
            (130102, "河北省", "石家庄市", "长安区", 114.5, 38.0, "河北长安区", 1),
        ],
    )
    conn.executemany(
        "INSERT INTO county_panel (county_code, year, grain_output_t, sown_kha, temp, prec, sun, log_yield)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [
            (110108, 2018, 12000.0, 3.0, 12.5, 500.0, 180.0, 9.4),
            (110108, 2019, 11000.0, 2.8, 13.1, 420.0, 190.0, 9.3),
            (130102, 2018, 210000.0, 60.0, 13.4, 538.0, 188.0, 12.2),
            (130102, 2019, 205000.0, 59.0, 13.9, 470.0, 192.0, 12.1),
        ],
    )
    conn.executemany(
        "INSERT INTO county_model_out"
        " (county_code, year, y_true, y_pred, clim_contrib, clim_anomaly, risk_level,"
        "  risk_pct, contrib_pct, unit_type, shap_temp, shap_prec, shap_sun)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (110108, 2018, 9.4, 9.3, -0.30, 0.13, 4, 22.0, 6.0, "farm", -0.10, 0.05, -0.25),
            (110108, 2019, 9.3, 9.2, -0.55, -0.13, 5, 8.0, 3.0, "farm", -0.20, 0.02, -0.33),
            (130102, 2018, 12.2, 12.4, 0.42, -0.19, 2, 71.0, 88.0, "farm", 0.30, -0.02, 0.14),
            (130102, 2019, 12.1, 12.3, 0.80, 0.19, 1, 95.0, 97.0, "farm", 0.55, -0.05, 0.30),
        ],
    )
    conn.executemany(
        "INSERT INTO feature_direction VALUES (?,?,?,?)",
        [("temp", 0.0373, 0.0123, 1), ("prec", -0.0029, 0.0057, 0), ("sun", 0.017, -0.0065, 0)],
    )
    conn.executemany(
        "INSERT INTO county_standard VALUES (?,?,?)",
        [
            ("transfer_5seed", "CLIM3|3|42|lco_r2", "0.2644"),
            ("transfer_5seed", "CLIM3|3|43|lco_r2", "0.2553"),
            ("transfer_5seed", "CLIMG|16|42|lco_r2", "0.4580"),
            ("transfer_5seed", "CLIMG|16|43|lco_r2", "0.4436"),
            ("transfer_5seed", "CLIMG|16|42|time_r2", "0.3609"),
            ("transfer_5seed", "CLIMG|16|43|time_r2", "0.3712"),
            ("null_permutation", "CLIM3|3|null_mean", "-0.0142"),
            ("null_permutation", "CLIM3|3|true_mean", "0.26"),
            ("null_permutation", "CLIM5|5|null_mean", "-0.0153"),
            ("null_permutation", "CLIMG|16|null_mean", "-0.0157"),
            ("null_permutation", "CLIMG|16|true_mean", "0.4489"),
            ("null_permutation", "CLIMG|16|frac_true_gt_null", "1.0"),
            ("single_yield_lco", "CLIMG|16|lco_r2", "0.5208"),
            ("bootstrap_delta", "CLIM3->CLIMG|delta_point", "0.1888"),
            ("bootstrap_delta", "CLIM3->CLIMG|ci_lo", "0.1241"),
        ],
    )
    conn.executemany(
        "INSERT INTO metadata VALUES (?,?)",
        [
            ("data_version", "v7-county"),
            ("climate_features", '["temp", "prec", "sun"]'),
            ("n_climate_features", "16"),
            ("agri_output_threshold_t", "10000"),
            ("model_trained_at", "2026-10-15T00:00:00+00:00"),
            ("model_scope_note", "test"),
            ("risk_index_definition", "risk from clim_anomaly"),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(county_repo, "DEFAULT_DB_PATH", db)
    return db


def test_list_counties_defaults_to_latest_year(client, county_db):
    resp = client.get("/api/counties")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["year"] == 2019
    assert body["data"]["count"] == 2
    assert {r["county"] for r in body["data"]["rows"]} == {"海淀区", "长安区"}
    # 风险等级降序：海淀区(5) 在前
    assert body["data"]["rows"][0]["county"] == "海淀区"


def test_list_counties_filters_and_errors(client, county_db):
    assert client.get("/api/counties?year=2018").get_json()["data"]["count"] == 2
    assert client.get("/api/counties?unit=farm").get_json()["data"]["count"] == 2
    assert client.get("/api/counties?province=北京市").get_json()["data"]["count"] == 1

    bad = client.get("/api/counties?year=abc")
    assert bad.status_code == 400
    assert bad.get_json()["error"]["code"] == 400

    out_of_range = client.get("/api/counties?year=1999")
    assert out_of_range.status_code == 400

    bad_unit = client.get("/api/counties?unit=city")
    assert bad_unit.status_code == 400


def test_county_history(client, county_db):
    ok = client.get("/api/counties/130102/history")
    assert ok.status_code == 200
    data = ok.get_json()["data"]
    assert data["county"]["map_key"] == "河北长安区"
    assert data["county"]["on_map"] is True
    assert [s["year"] for s in data["series"]] == [2018, 2019]
    assert data["series"][0]["grain_output_t"] == 210000.0
    assert data["series"][0]["clim_anomaly"] == pytest.approx(-0.19)

    missing = client.get("/api/counties/999999/history")
    assert missing.status_code == 404


def test_county_attribution(client, county_db):
    resp = client.get("/api/counties/130102/attribution?year=2018")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["available"] is True
    assert data["summary"]["risk_level"] == 2

    items = data["items"]
    assert len(items) == len(county_repo.FEATURE_DICT)  # 16 维全返回
    top = items[0]
    assert top["feature"] == "temp"  # |0.30| 最大
    assert top["label"] == "年均气温"
    assert top["value"] == pytest.approx(13.4)
    assert top["direction_stable"] is True
    # 未提供值/方向的维度不报错，只是 None
    assert any(i["shap"] is None for i in items)

    assert client.get("/api/counties/130102/attribution").status_code == 400
    assert client.get("/api/counties/130102/attribution?year=x").status_code == 400
    assert client.get("/api/counties/999999/attribution?year=2018").status_code == 404


def test_county_meta_endpoints(client, county_db):
    summary = client.get("/api/counties/meta/summary").get_json()["data"]
    assert summary["scored_rows"] == 4
    assert summary["counties"] == 2
    assert summary["years"] == [2018, 2019]
    assert summary["agri_output_threshold_t"] == 10000
    assert summary["risk_index_definition"] == "risk from clim_anomaly"
    assert summary["year_coverage"] == [
        {"year": 2018, "scored": 2, "truth": 2},
        {"year": 2019, "scored": 2, "truth": 2},
    ]
    assert {p["province"] for p in summary["provinces"]} == {"北京市", "河北省"}

    standard = client.get("/api/counties/meta/standard").get_json()["data"]
    levels = [row["level"] for row in standard["ladder"]]
    assert levels[0].startswith("省级")
    assert any("CLIMG（16 维）" in lv for lv in levels)
    climg = next(r for r in standard["ladder"] if "CLIMG（16 维）" in r["level"])
    assert climg["lco_r2"].startswith("+0.4508")  # (0.4580+0.4436)/2 = 0.4508
    assert "-0.0157" in climg["lco_r2"]           # null 对照同格展示
    assert standard["bootstrap"]["delta_point"] == "0.1888"
    # 阴性对照与规模诊断分开两组，测试库只灌了 null_permutation
    assert [n["config"] for n in standard["nulls"]] == ["CLIM3", "CLIM5", "CLIMG"]
    assert standard["nulls"][2]["null_mean"] == "-0.0157"
    assert standard["nulls"][2]["frac_true_gt_null"] == "1.0"
    assert standard["scale_diagnosis"] == {}      # 测试库未灌 scope_diagnosis
    assert standard["scale_note"] is None


def test_county_endpoints_503_when_db_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(county_repo, "DEFAULT_DB_PATH", tmp_path / "nope.db")
    for url in ("/api/counties", "/api/counties/meta/summary", "/api/counties/meta/standard",
                "/api/counties/130102/history", "/api/counties/130102/attribution?year=2018"):
        resp = client.get(url)
        assert resp.status_code == 503, url
        assert resp.get_json()["error"]["code"] == 503
