"""M03 玉米长势 API 的契约测试。"""

from __future__ import annotations


def test_maize_counties_returns_panel(client):
    resp = client.get("/api/growth/counties")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    data = body["data"]
    assert data["count"] >= 600
    assert len(data["rows"]) == data["count"]
    assert {z["key"] for z in data["zones"]} == {"NE", "HHH", "SW"}


def test_simulate_baseline_is_100(client):
    rows = client.get("/api/growth/counties").get_json()["data"]["rows"]
    row = next(r for r in rows if r["code"] == 411623)
    resp = client.post(
        "/api/growth/simulate",
        json={
            "county_code": row["code"],
            "d_temp": 0,
            "d_prec_pct": 0,
            "d_heat_days": 0,
            "irrigation": row["irr"],
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["gsi"] == 100.0
    assert data["delta_pct"] == 0.0
    assert data["baseline"]["gdd"] == data["scenario"]["gdd"]


def test_simulate_hotter_drier_is_worse(client):
    resp = client.post(
        "/api/growth/simulate",
        json={
            "county_code": 411623,
            "d_temp": 2,
            "d_prec_pct": -20,
            "d_heat_days": 10,
            "irrigation": 0.5,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["gsi"] < 100
    assert data["limiting_label"] in {"积温不足", "水分亏缺", "抽雄期热害"}


def test_simulate_rejects_unknown_county(client):
    resp = client.post("/api/growth/simulate", json={"county_code": 999999})
    assert resp.status_code == 404


def test_simulate_rejects_out_of_range_params(client):
    resp = client.post(
        "/api/growth/simulate",
        json={"county_code": 411623, "d_temp": 9},
    )
    assert resp.status_code == 400
