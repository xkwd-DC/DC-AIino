"""backend/services/panel_repo.py — Repository pattern for grain.db

Phase 4 持久层读路径。封装 SQLite 查询,api 层只看 Python dict/list。

设计要点
========
1. **不在 import 时打开 db** — Repository 是无状态的,每次方法调用临时连接 + 关闭。
   测试环境 grain.db 不存在不报错,api 层 catch RepoUnavailable 走 fallback baseline json。
2. **参数化查询** — `?` 占位符,严防 SQL 注入(`province` 来自 URL 中文)。
3. **`sqlite3.Row` row_factory** — 行可像 dict 访问,便于 `dict(row)` 序列化。
4. **显式异常** — 调用方能区分 `ProvinceNotFound` / `YearOutOfRange` / `RepoUnavailable`,
   返不同 HTTP 状态码(404 / 400 / 503)。
5. **Read-only 模式连接** — 用 `?mode=ro` URI 表明意图,SQLite 拒绝意外写。

依赖
====
- sqlite3 (标准库)
- backend/data/grain.db (Phase 4 ETL `scripts/load_panel_to_db.py --reset` 生成)
- backend/data/schema.sql 定义的表 (PR #28 feat/phase4-schema)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

# ====================================================================
# 路径 & 常量
# ====================================================================

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "grain.db"

MIN_YEAR = 2011
MAX_YEAR = 2023
EXPECTED_PROVINCES = 31

# 11 features (对齐 schema.sql 与 inference.py)
FEATURE_COLS = [
    "ndvi", "temp", "prec", "sun", "spei", "drou_a",
    "flood_a", "flood_r", "irr", "fert", "mech",
]


# ====================================================================
# 异常
# ====================================================================

class RepoError(Exception):
    """Repository 基类异常。"""


class RepoUnavailable(RepoError):
    """grain.db 不存在 / 不可读 — api 层应 fallback。"""


class ProvinceNotFound(RepoError):
    """请求的省份不在 31 省里。"""

    def __init__(self, province: str) -> None:
        super().__init__(f"province not in 31-province set: {province!r}")
        self.province = province


class YearOutOfRange(RepoError):
    """请求的年份不在 [2011, 2023]。"""

    def __init__(self, year: int) -> None:
        super().__init__(f"year {year} not in [{MIN_YEAR}, {MAX_YEAR}]")
        self.year = year


# ====================================================================
# 内部工具
# ====================================================================

def _open_ro(db_path: Path) -> sqlite3.Connection:
    """打开 db,read-only 模式。文件不存在时 raise RepoUnavailable。

    SQLite URI: file:/path?mode=ro&immutable=1 ,immutable 启用更激进的查询缓存。
    """
    if not db_path.exists():
        raise RepoUnavailable(f"grain.db not found at {db_path}")

    # uri=True 才能用 file: 协议指定 mode=ro
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _validate_year(year: int) -> None:
    if not (MIN_YEAR <= year <= MAX_YEAR):
        raise YearOutOfRange(year)


# ====================================================================
# 公开 API
# ====================================================================

def is_available(db_path: Optional[Path] = None) -> bool:
    """是否可以查询 grain.db。api 层用来选 repo 或 fallback。"""
    return (db_path or DEFAULT_DB_PATH).exists()


def get_latest_year(db_path: Optional[Path] = None) -> int:
    """grain.db 中实际最大的年份。Phase 4 后预期 2023。"""
    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        row = conn.execute("SELECT MAX(year) AS y FROM yearly_panel").fetchone()
        if row is None or row["y"] is None:
            raise RepoUnavailable("yearly_panel 表无数据")
        return int(row["y"])


def get_provinces_meta(db_path: Optional[Path] = None) -> list[dict]:
    """31 省静态属性(name / name_en / region)。供前端做大区分组。"""
    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        rows = conn.execute(
            "SELECT name, name_en, region FROM provinces ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_panel_by_year(year: int,
                       db_path: Optional[Path] = None) -> list[dict]:
    """返某年的 31 省面板数据。

    Args:
        year: 2011 - 2023

    Returns:
        长度 31 的 list[dict],每行含 province / year / yield_kg_per_ha /
        y_butter / y_linear / 11 features / region

    Raises:
        YearOutOfRange: year ∉ [2011, 2023]
        RepoUnavailable: grain.db 不存在
    """
    _validate_year(year)
    path = db_path or DEFAULT_DB_PATH

    sql = """
        SELECT p.name AS province,
               p.name_en,
               p.region,
               y.year,
               y.yield_kg_per_ha,
               y.y_butter,
               y.y_linear,
               y.ndvi, y.temp, y.prec, y.sun, y.spei,
               y.drou_a, y.flood_a, y.flood_r,
               y.irr, y.fert, y.mech
        FROM yearly_panel y
        JOIN provinces p ON p.name = y.province
        WHERE y.year = ?
        ORDER BY p.name
    """

    with _open_ro(path) as conn:
        rows = conn.execute(sql, (year,)).fetchall()
        return [dict(r) for r in rows]


def get_history(province: str,
                 db_path: Optional[Path] = None) -> dict:
    """返某省 2011-2023 时间序列。M01 风险地图省份明细卡用。

    Args:
        province: 中文省名,如 "河南"

    Returns:
        {
            "province": "河南",
            "name_en": "henan",
            "region": "华中",
            "series": [{year, yield, y_butter, ...}, x13]
        }

    Raises:
        ProvinceNotFound: province 不在 31 省
        RepoUnavailable: grain.db 不存在
    """
    path = db_path or DEFAULT_DB_PATH

    with _open_ro(path) as conn:
        prov_row = conn.execute(
            "SELECT name, name_en, region FROM provinces WHERE name = ?",
            (province,)
        ).fetchone()
        if prov_row is None:
            raise ProvinceNotFound(province)

        series_sql = """
            SELECT year, yield_kg_per_ha, y_butter, y_linear,
                   ndvi, temp, prec, sun, spei,
                   drou_a, flood_a, flood_r, irr, fert, mech
            FROM yearly_panel
            WHERE province = ?
            ORDER BY year
        """
        series_rows = conn.execute(series_sql, (province,)).fetchall()

        return {
            "province": prov_row["name"],
            "name_en": prov_row["name_en"],
            "region": prov_row["region"],
            "series": [dict(r) for r in series_rows],
        }


def get_metadata(db_path: Optional[Path] = None) -> dict[str, str]:
    """读 metadata 表(loaded_at / parquet_md5 / 等)。供 /api/health 或 debug 用。"""
    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        rows = conn.execute("SELECT key, value FROM metadata").fetchall()
        return {r["key"]: r["value"] for r in rows}
