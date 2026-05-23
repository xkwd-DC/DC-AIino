#!/usr/bin/env python3
"""scripts/load_panel_to_db.py — paper_panel_v3.parquet → backend/data/grain.db

Phase 4 (5/27-28) ETL 入口,把石灵子的 v3 面板 parquet 灌入 SQLite,
供 backend/api/provinces.py 的 /api/provinces?year= 和 /history 查询。

设计要点
========
1. **Idempotent** — 同一 parquet 多跑不会出错。`--reset` 时 DROP + 重建,
   否则用 INSERT OR REPLACE (yearly_panel 是 (province, year) PK)。
2. **列名 case-insensitive** — parquet 列名是 `NDVI/Temp/Prec`(熊鑫风格),
   schema 列名是 `ndvi/temp/prec`(小写)。脚本内做映射。
3. **y_butter / y_linear 智能** — 若 parquet 已含(石灵子 v3 已经做了)直接 read;
   缺失才计算。两个去趋势 Y 都是按省分组 (groupby + transform)。
4. **省份完整性 assert** — 31 省 × 13 年 = 403 行,任何缺省都 panic。
5. **NDVI 强制** — v3 必须含 NDVI,缺则 panic(论文 §3.3 11 维硬指标)。
6. **元数据时戳 + md5** — metadata 表写 loaded_at + parquet_md5,供 audit。
7. **SUMMARY 打印** — 跑完打 rows / years / size,供 CI / 手动验证。

用法
====
    python scripts/load_panel_to_db.py \\
        --parquet data/interim/paper_panel_v3.parquet \\
        --db backend/data/grain.db \\
        --reset

依赖
====
- pandas >= 2.0
- scipy >= 1.10
- numpy >= 1.24
- pyarrow >= 14 (read_parquet 后端)

在 GCP Python 3.11 venv:
    pip install pandas scipy numpy pyarrow

—— Phase 4 落地,协调中心整夜 loop [B] (2026-05-22)
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# 三方依赖在 import 时即报错(GCP Python 3.11 venv 装齐后跑)
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt

# ====================================================================
# 常量
# ====================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PARQUET = PROJECT_ROOT / "data" / "interim" / "paper_panel_v3.parquet"
DEFAULT_DB = PROJECT_ROOT / "backend" / "data" / "grain.db"
SCHEMA_SQL = PROJECT_ROOT / "backend" / "data" / "schema.sql"

EXPECTED_YEARS = list(range(2011, 2024))  # 2011..2023 = 13 年
EXPECTED_PROVINCES_COUNT = 31

# parquet 列名(熊鑫 inference.py 风格)→ schema 列名映射
# Key = schema column (小写下划线),Value = parquet 列候选(大小写多种,优先匹配)
COLUMN_MAP: dict[str, list[str]] = {
    # target
    "yield_kg_per_ha": ["yield_kg_per_ha", "yield", "y", "Y"],
    # 去趋势 Y(若 v3 已含直接 read,否则计算)
    "y_butter": ["y_butter", "Y_butter"],
    "y_linear": ["y_linear", "Y_linear"],
    # 11 features
    "ndvi": ["NDVI", "ndvi"],
    "temp": ["Temp", "temp"],
    "prec": ["Prec", "prec"],
    "sun": ["Sun", "sun"],
    "spei": ["SPEI", "spei"],
    "drou_a": ["Drou_A", "drou_a", "DROU_A"],
    "flood_a": ["Flood_A", "flood_a", "FLOOD_A"],
    "flood_r": ["Flood_R", "flood_r", "FLOOD_R", "flood"],  # PR #21: parquet 是 flood
    "irr": ["Irr", "irr"],
    "fert": ["Fert", "fert"],
    "mech": ["Mech", "mech"],
}

# 31 省 → 7 大区(M01 风险地图聚合用)
PROVINCE_TO_REGION: dict[str, str] = {
    # 华北 5
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    # 东北 3
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
    # 华东 7
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东",
    "福建": "华东", "江西": "华东", "山东": "华东",
    # 华中 3
    "河南": "华中", "湖北": "华中", "湖南": "华中",
    # 华南 3
    "广东": "华南", "广西": "华南", "海南": "华南",
    # 西南 5
    "重庆": "西南", "四川": "西南", "贵州": "西南", "云南": "西南", "西藏": "西南",
    # 西北 5
    "陕西": "西北", "甘肃": "西北", "青海": "西北", "宁夏": "西北", "新疆": "西北",
}

# 31 省 → 英文 slug (URL 用)
PROVINCE_TO_SLUG: dict[str, str] = {
    "北京": "beijing", "天津": "tianjin", "河北": "hebei", "山西": "shanxi",
    "内蒙古": "inner-mongolia",
    "辽宁": "liaoning", "吉林": "jilin", "黑龙江": "heilongjiang",
    "上海": "shanghai", "江苏": "jiangsu", "浙江": "zhejiang", "安徽": "anhui",
    "福建": "fujian", "江西": "jiangxi", "山东": "shandong",
    "河南": "henan", "湖北": "hubei", "湖南": "hunan",
    "广东": "guangdong", "广西": "guangxi", "海南": "hainan",
    "重庆": "chongqing", "四川": "sichuan", "贵州": "guizhou", "云南": "yunnan",
    "西藏": "tibet",
    "陕西": "shaanxi", "甘肃": "gansu", "青海": "qinghai", "宁夏": "ningxia",
    "新疆": "xinjiang",
}

assert len(PROVINCE_TO_REGION) == EXPECTED_PROVINCES_COUNT, "省份映射数量错"
assert len(PROVINCE_TO_SLUG) == EXPECTED_PROVINCES_COUNT, "slug 映射数量错"
assert set(PROVINCE_TO_REGION) == set(PROVINCE_TO_SLUG), "省份名集合不一致"


# ====================================================================
# 工具函数
# ====================================================================

def resolve_column(df: pd.DataFrame, schema_col: str) -> str | None:
    """从 parquet 找 schema_col 对应的实际列名,case-insensitive 候选匹配。

    Returns:
        实际列名,或 None(未找到)
    """
    candidates = COLUMN_MAP.get(schema_col, [schema_col])
    df_cols_lower = {c.lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
        # 再做 case-insensitive fallback
        if candidate.lower() in df_cols_lower:
            return df_cols_lower[candidate.lower()]
    return None


def compute_butterworth_residual(series: pd.Series, order: int = 2,
                                  normal_cutoff: float = 0.2) -> np.ndarray:
    """按省时间序列做 Butterworth lowpass + filtfilt,返残差(真值 - 趋势)。

    Args:
        series: 13 年的 yield 序列(单省)
        order: 滤波器阶数
        normal_cutoff: 归一化截止频率(0-1),0.2 对 13 年序列约对应 5 年滑窗

    Returns:
        13 长 np.array,残差(可负)
    """
    y = series.values.astype(np.float64)
    if len(y) < 4:
        # 序列太短无法 filtfilt,返 0 残差
        return np.zeros_like(y)

    b, a = butter(order, normal_cutoff, btype="low")
    # 镜像 padding 减边界伪影 (filtfilt 默认 padlen 即可,scipy >=1.10)
    trend = filtfilt(b, a, y, method="gust")  # gustafsson 边界处理
    return y - trend


def compute_linear_residual(series: pd.Series) -> np.ndarray:
    """按省时间序列做 1 阶线性回归,返残差。

    简单基线,对比 Butterworth 的方法学消融。
    """
    y = series.values.astype(np.float64)
    x = np.arange(len(y), dtype=np.float64)
    if len(y) < 2:
        return np.zeros_like(y)
    slope, intercept = np.polyfit(x, y, 1)
    trend = slope * x + intercept
    return y - trend


def md5_of_file(path: Path) -> str:
    """计算文件 md5(用于 metadata audit)。"""
    h = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ====================================================================
# 主流程
# ====================================================================

def load_and_validate(parquet_path: Path) -> pd.DataFrame:
    """读 parquet + 列名解析 + 完整性 assert。

    Returns:
        normalized DataFrame,列名已重命名为 schema 风格,含 province / year / target / 11 features
    """
    print(f"[load] reading {parquet_path}")
    df = pd.read_parquet(parquet_path)
    print(f"[load] raw shape: {df.shape}")
    print(f"[load] raw columns: {list(df.columns)}")

    # 必须有 province + year(几乎不可能列名变,但仍 case-insensitive 找)
    province_col = next((c for c in ["province", "Province", "PROVINCE", "省份"]
                         if c in df.columns), None)
    year_col = next((c for c in ["year", "Year", "YEAR", "年份"]
                     if c in df.columns), None)
    if province_col is None or year_col is None:
        raise SystemExit(f"[FATAL] parquet 缺 province/year 列,实际列: {list(df.columns)}")

    # 解析 11 features + target,缺 NDVI 立即 panic
    rename_map: dict[str, str] = {province_col: "province", year_col: "year"}
    feature_cols = ["ndvi", "temp", "prec", "sun", "spei", "drou_a",
                    "flood_a", "flood_r", "irr", "fert", "mech"]
    for schema_col in ["yield_kg_per_ha", "y_butter", "y_linear", *feature_cols]:
        actual = resolve_column(df, schema_col)
        if actual is None:
            if schema_col == "ndvi":
                raise SystemExit("[FATAL] parquet 缺 NDVI 列 — v3 必含 (论文 §3.3 11 维)")
            if schema_col in ("y_butter", "y_linear"):
                # 这两个允许缺失,后面计算
                continue
            if schema_col == "yield_kg_per_ha":
                raise SystemExit(f"[FATAL] parquet 缺 target 列 yield_kg_per_ha")
            # 11 features 之一缺失 — 给警告但不 panic (Phase 4 v1 容错)
            print(f"[warn] parquet 缺 {schema_col} (候选: {COLUMN_MAP.get(schema_col)})")
        else:
            rename_map[actual] = schema_col

    df = df.rename(columns=rename_map)

    # year 整数化
    df["year"] = df["year"].astype(int)

    # 完整性 assert: 31 省 × 13 年 = 403 行
    actual_provinces = set(df["province"].unique())
    expected_provinces = set(PROVINCE_TO_REGION.keys())
    if actual_provinces != expected_provinces:
        missing = expected_provinces - actual_provinces
        extra = actual_provinces - expected_provinces
        raise SystemExit(
            f"[FATAL] 省份集合不符\n"
            f"  缺: {missing or '(无)'}\n"
            f"  多: {extra or '(无)'}"
        )

    actual_years = set(df["year"].unique())
    expected_years_set = set(EXPECTED_YEARS)
    if actual_years != expected_years_set:
        raise SystemExit(
            f"[FATAL] 年份集合不符\n"
            f"  实际: {sorted(actual_years)}\n"
            f"  期望: {EXPECTED_YEARS}"
        )

    # 每省 13 年完整 assert
    province_year_count = df.groupby("province").size()
    bad = province_year_count[province_year_count != len(EXPECTED_YEARS)]
    if len(bad) > 0:
        raise SystemExit(f"[FATAL] 以下省份年份不全(应 13):\n{bad}")

    if len(df) != EXPECTED_PROVINCES_COUNT * len(EXPECTED_YEARS):
        raise SystemExit(
            f"[FATAL] 行数 {len(df)} ≠ "
            f"{EXPECTED_PROVINCES_COUNT}×{len(EXPECTED_YEARS)}={EXPECTED_PROVINCES_COUNT * len(EXPECTED_YEARS)}"
        )

    print(f"[load] validated: {len(df)} rows, {len(actual_provinces)} provinces × "
          f"{len(actual_years)} years")
    return df


def compute_detrended_y_if_missing(df: pd.DataFrame) -> pd.DataFrame:
    """若 y_butter / y_linear 缺失,按省分组计算。

    DataFrame 必须先按 (province, year) 排好。
    """
    df = df.sort_values(["province", "year"]).reset_index(drop=True)

    if "y_butter" not in df.columns:
        print("[detrend] computing y_butter (Butterworth filtfilt order=2 cutoff=0.2)")
        df["y_butter"] = df.groupby("province", group_keys=False)["yield_kg_per_ha"].transform(
            compute_butterworth_residual
        )
    else:
        print("[detrend] y_butter already in parquet, skipping")

    if "y_linear" not in df.columns:
        print("[detrend] computing y_linear (np.polyfit deg=1)")
        df["y_linear"] = df.groupby("province", group_keys=False)["yield_kg_per_ha"].transform(
            compute_linear_residual
        )
    else:
        print("[detrend] y_linear already in parquet, skipping")

    return df


def write_to_sqlite(df: pd.DataFrame, db_path: Path, parquet_path: Path,
                    reset: bool) -> None:
    """落到 SQLite,先 schema 后数据。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if reset and db_path.exists():
        print(f"[db] --reset, removing existing {db_path}")
        db_path.unlink()

    print(f"[db] connecting {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        # 1) schema (idempotent via IF NOT EXISTS)
        print(f"[db] applying schema from {SCHEMA_SQL}")
        with SCHEMA_SQL.open(encoding="utf-8") as f:
            conn.executescript(f.read())

        # 2) provinces 表
        print("[db] inserting 31 provinces")
        provinces_rows = [
            (name, PROVINCE_TO_SLUG[name], PROVINCE_TO_REGION[name])
            for name in sorted(PROVINCE_TO_REGION.keys())
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO provinces (name, name_en, region) VALUES (?, ?, ?)",
            provinces_rows
        )

        # 3) yearly_panel
        feature_cols = ["ndvi", "temp", "prec", "sun", "spei", "drou_a",
                        "flood_a", "flood_r", "irr", "fert", "mech"]
        insert_cols = ["province", "year", "yield_kg_per_ha", "y_butter", "y_linear", *feature_cols]
        placeholders = ", ".join(["?"] * len(insert_cols))
        cols_csv = ", ".join(insert_cols)
        sql = f"INSERT OR REPLACE INTO yearly_panel ({cols_csv}) VALUES ({placeholders})"
        rows = [
            tuple(None if pd.isna(row.get(col)) else row[col] for col in insert_cols)
            for _, row in df.iterrows()
        ]
        print(f"[db] inserting {len(rows)} rows into yearly_panel")
        conn.executemany(sql, rows)

        # 4) metadata 时戳
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        md5 = md5_of_file(parquet_path)
        metadata_rows = [
            ("loaded_at", now_iso),
            ("source_parquet", str(parquet_path.relative_to(PROJECT_ROOT))),
            ("parquet_md5", md5),
            ("rows_loaded", str(len(rows))),
            ("provinces_loaded", str(len(provinces_rows))),
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            metadata_rows
        )

        conn.commit()
        print("[db] committed")
    finally:
        conn.close()


def print_summary(db_path: Path) -> None:
    """跑完读 db 打印 summary,供肉眼/CI 验证。"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        provinces = cur.execute("SELECT COUNT(*) FROM provinces").fetchone()[0]
        panel_rows = cur.execute("SELECT COUNT(*) FROM yearly_panel").fetchone()[0]
        years = cur.execute(
            "SELECT MIN(year), MAX(year), COUNT(DISTINCT year) FROM yearly_panel"
        ).fetchone()
        md5 = cur.execute("SELECT value FROM metadata WHERE key='parquet_md5'").fetchone()[0]
        loaded_at = cur.execute("SELECT value FROM metadata WHERE key='loaded_at'").fetchone()[0]

        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  provinces:    {provinces} (expected 31)")
        print(f"  panel rows:   {panel_rows} (expected 403)")
        print(f"  years range:  {years[0]}..{years[1]} ({years[2]} years)")
        print(f"  parquet md5:  {md5}")
        print(f"  loaded_at:    {loaded_at}")
        print(f"  db path:      {db_path}")
        print(f"  db size:      {db_path.stat().st_size:,} bytes")
        print("=" * 60)
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Load paper_panel_v3.parquet into SQLite (Phase 4)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法")[1] if __doc__ and "用法" in __doc__ else None,
    )
    p.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET,
                   help=f"输入 parquet 路径 (default: {DEFAULT_PARQUET})")
    p.add_argument("--db", type=Path, default=DEFAULT_DB,
                   help=f"输出 SQLite 路径 (default: {DEFAULT_DB})")
    p.add_argument("--reset", action="store_true",
                   help="先删现有 db 文件,完全重建(建议每次都加,避免老脏数据)")
    args = p.parse_args()

    if not args.parquet.exists():
        print(f"[FATAL] parquet not found: {args.parquet}", file=sys.stderr)
        return 1
    if not SCHEMA_SQL.exists():
        print(f"[FATAL] schema not found: {SCHEMA_SQL}", file=sys.stderr)
        return 1

    df = load_and_validate(args.parquet)
    df = compute_detrended_y_if_missing(df)
    write_to_sqlite(df, args.db, args.parquet, args.reset)
    print_summary(args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
