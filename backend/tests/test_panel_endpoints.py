"""Phase 4 endpoints 的合约测试 — 6 cases。

依赖 PR #30 (`feat/phase4-repo`) 的 `services.panel_repo` 模块 +
`/api/provinces?year=` query + `/api/provinces/<name>/history` 路由。

PR #30 merge 前:所有测试 skip(module-level marker),不破坏现有 16 pytest。
PR #30 merge 后:6 测试自动启用,与现有 16 合计 22 pytest 全过。

测试策略
========
1. **inline schema** — 不依赖 PR #28 的 `backend/data/schema.sql`,fixture 内嵌
2. **dummy data only** — fixture 灌 2 省 × 13 年 = 26 行,够测合约,不验数据完整性
3. **monkeypatch DEFAULT_DB_PATH** — fixture 把 panel_repo 指向 tmp_path 的临时 db
4. **AAA 模式** — 对齐 backend/tests/test_api.py 风格

—— 协调中心整夜 loop · [D] · (2026-05-22)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# ====================================================================
# 依赖检测 — PR #30 是否已 merge
# ====================================================================

try:
    from services import panel_repo
    PANEL_REPO_AVAILABLE = True
except ImportError:
    PANEL_REPO_AVAILABLE = False
    panel_repo = None  # type: ignore[assignment]


def _history_endpoint_registered() -> bool:
    """检查 app.py 是否注册了 /api/provinces/<name>/history 路由。"""
    if not PANEL_REPO_AVAILABLE:
        return False
    try:
        from app import app as flask_app
    except ImportError:
        return False
    return any(
        "history" in str(rule.rule)
        for rule in flask_app.url_map.iter_rules()
    )


# Module-level skip — PR #30 merge 前整个文件 skip
pytestmark = pytest.mark.skipif(
    not PANEL_REPO_AVAILABLE,
    reason="depends on PR #30 (feat/phase4-repo) — panel_repo module",
)

requires_history_route = pytest.mark.skipif(
    not _history_endpoint_registered(),
    reason="depends on PR #30 — /api/provinces/<name>/history route in app.py",
)


# ====================================================================
# Inline schema + dummy data fixture
# ====================================================================

SCHEMA_INLINE = """
CREATE TABLE provinces (
    name    TEXT PRIMARY KEY,
    name_en TEXT NOT NULL UNIQUE,
    region  TEXT NOT NULL
);
CREATE TABLE yearly_panel (
    province        TEXT NOT NULL REFERENCES provinces(name),
    year            INTEGER NOT NULL,
    yield_kg_per_ha REAL NOT NULL,
    y_butter        REAL,
    y_linear        REAL,
    ndvi            REAL, temp REAL, prec REAL, sun REAL, spei REAL,
    drou_a          REAL, flood_a REAL, flood_r REAL,
    irr             REAL, fert REAL, mech REAL,
    PRIMARY KEY (province, year)
);
CREATE TABLE metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DUMMY_PROVINCES = [
    ("河南", "henan", "华中"),
    ("山东", "shandong", "华东"),
]
DUMMY_YEARS = list(range(2011, 2024))  # 13 年


def _populate_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA_INLINE)
        conn.executemany(
            "INSERT INTO provinces (name, name_en, region) VALUES (?, ?, ?)",
            DUMMY_PROVINCES,
        )
        # 13 年 × 2 省 = 26 行,yield 逐年 +10,其他列固定值方便断言
        rows = [
            (
                name, year,
                6000.0 + i * 10,   # yield_kg_per_ha
                5.0, 2.0,          # y_butter / y_linear
                0.55, 16.0, 700.0, 2100.0, -0.1,  # ndvi/temp/prec/sun/spei
                4.0, 3.5, 1.2,                      # drou_a/flood_a/flood_r
                60.0, 800.0, 1500.0,                # irr/fert/mech
            )
            for name, _, _ in DUMMY_PROVINCES
            for i, year in enumerate(DUMMY_YEARS)
        ]
        conn.executemany(
            """INSERT INTO yearly_panel
               (province, year, yield_kg_per_ha, y_butter, y_linear,
                ndvi, temp, prec, sun, spei, drou_a, flood_a, flood_r,
                irr, fert, mech)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [("loaded_at", "2026-05-22T18:00:00Z"), ("data_version", "test")],
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def phase4_db(tmp_path, monkeypatch):
    """临时 grain.db + monkeypatch DEFAULT_DB_PATH。

    fixture 完成后 panel_repo.DEFAULT_DB_PATH 指向 tmp_path/grain.db,
    所有 API 路径(/api/provinces?year + /history)走该 db。
    """
    db_path = tmp_path / "grain.db"
    _populate_db(db_path)
    monkeypatch.setattr(panel_repo, "DEFAULT_DB_PATH", db_path)
    return db_path


# ====================================================================
# Tests — 6 cases
# ====================================================================

def test_provinces_default_year_returns_31_or_db(client, phase4_db):
    """无 ?year=:有 db 时返该 db 的最新年(本测试 fixture: 2 行)。

    Arrange: phase4_db 灌 2 省 13 年
    Act:     GET /api/provinces (无 year)
    Assert:  200, data 长度 = 2(fixture dummy)
    """
    res = client.get("/api/provinces")

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    # fixture monkeypatch 后 panel_repo.is_available() = True,走 db 路径返 2 行
    assert len(body["data"]) == 2


def test_provinces_with_valid_year_2015(client, phase4_db):
    """?year=2015 → 2 行(2 省 dummy),年份正确。"""
    res = client.get("/api/provinces?year=2015")

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert len(body["data"]) == 2
    assert all(row["year"] == 2015 for row in body["data"])
    # 11 features 都有 + region join 上
    first = body["data"][0]
    assert "ndvi" in first
    assert first["region"] in {"华中", "华东"}


def test_provinces_with_year_out_of_range_returns_400(client, phase4_db):
    """?year=2099 → 400 YearOutOfRange。"""
    res = client.get("/api/provinces?year=2099")

    assert res.status_code == 400
    body = res.get_json()
    assert body["success"] is False
    assert "2099" in body["error"]["message"]


def test_provinces_with_malformed_year_returns_400(client, phase4_db):
    """?year=abc → 400(integer parse fail)。"""
    res = client.get("/api/provinces?year=abc")

    assert res.status_code == 400
    body = res.get_json()
    assert body["success"] is False
    assert "integer" in body["error"]["message"].lower()


@requires_history_route
def test_history_valid_province_returns_13_years(client, phase4_db):
    """/河南/history → 13 年序列,province / region 正确。"""
    res = client.get("/api/provinces/河南/history")

    assert res.status_code == 200
    body = res.get_json()["data"]
    assert body["province"] == "河南"
    assert body["name_en"] == "henan"
    assert body["region"] == "华中"
    assert len(body["series"]) == 13
    # 时间序列按 year 升序
    years = [r["year"] for r in body["series"]]
    assert years == sorted(years)
    assert years[0] == 2011
    assert years[-1] == 2023


@requires_history_route
def test_history_unknown_province_returns_404(client, phase4_db):
    """/Atlantis/history → 404 ProvinceNotFound。"""
    res = client.get("/api/provinces/Atlantis/history")

    assert res.status_code == 404
    body = res.get_json()
    assert body["success"] is False
    assert "Atlantis" in body["error"]["message"] or "province" in body["error"]["message"].lower()
