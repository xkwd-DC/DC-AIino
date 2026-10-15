#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v9 Step 1：县级面板落地为站点可查的 SQLite（backend/data/county.db）。

背景
====
站点此前只服务省级 v3 面板（31 省 × 13 年 = 403 行，backend/data/grain.db），
而县级的成品面板（paper_panel_v7_prediction.parquet，1199 县 × 12 年 = 14388 行）
只存在于实验脚本与报告里。本脚本把县级面板做成**只读查询层**，供新 API 使用，
不改动 grain.db（省级模块零回归）。

产出
====
1. backend/data/county.db
     county_meta       1199 县静态属性（代码 / 名称 / 城市 / 省份 / 经纬度）
     county_panel      14388 行 × 目标 + 特征（对齐 v7 列，列名英文化）
     county_standard   数据口径与协议数字（供前端"迁移体检"面板直读，禁止硬编码）
     metadata          k-v 元信息（来源 parquet / md5 / 行数 / 构建时间）
2. frontend/public/maps/counties_10provinces.json
     10 主产省县级边界（天地图 GS(2024)0650），坐标降精度 + 重写 name 为唯一键，
     以便 ECharts 按 name 精确着色（同名的 5 个「市辖区」类县名加省份前缀）。

⚠️ 列名坑
=========
parquet 前 17 列是中文列名（GBK 遗留）。本脚本用显式映射表转换，不按位置索引。

用法
====
    python scripts/data/v9_01_build_county_site_db.py
    python scripts/data/v9_01_build_county_site_db.py --check-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"
GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "counties_10provinces_GS2024.geojson"
DB = PROJECT_ROOT / "backend" / "data" / "county.db"
WEB_MAP = PROJECT_ROOT / "frontend" / "public" / "maps" / "counties_10provinces.json"

# ── 中文列名 → 语义列名（显式映射，禁止按位置索引） ──────────────────────────
CN_TO_EN = {
    "区县代码": "county_code",
    "省份": "province",
    "城市": "city",
    "区县": "county",
    "年份": "year",
    "粮食总产量_吨": "grain_output_t",
    "农作物总播种面积_千公顷": "sown_kha",
    "常用耕地面积_公顷": "arable_ha",
    "机收面积_公顷": "mech_harvest_ha",
    "设施农业占地面积_公顷": "facility_ha",
    "农用机械总动力_千万瓦": "mech_power_10mw",
    "农林牧渔业总产值_万元": "agri_output_wan",
    "农业增加值_万元": "agri_gva_wan",
    "第一产业增加值_万元": "primary_gva_wan",
    "乡村人口_万人": "rural_pop_wan",
    "乡村从业人员数_人": "rural_employed",
    "农林牧渔业从业人员数_人": "agri_employed",
}

# ── 站点县级模型的气候特征集 CLIMG（16 维） ────────────────────────────────
# 与 scripts/data/v6_12_climate_transfer.py 的 CLIMG 完全一致：
# 不含播种面积/规模（log_sown）、不含省-年共享常量。这是"气候解释力"的干净口径。
CLIMATE_FEATURES = [
    # 县级年均气候（TerraClimate 4.6km，县治最近格点）
    "temp", "prec", "sun",
    # 县级 SPEI（SPEIbase v2.10 0.5°，县级优先、省级回填）
    "spei_annual_mean", "spei_growing_season_mean",
    # 生长季 / 极端 / 季节指数（TerraClimate 月度派生）
    "gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
    "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
    "winter_temp", "seasonal_temp_range",
]

# 面板中一并入库、供前端展示与地图着色的其余列
EXTRA_COLUMNS = [
    "grain_output_t", "sown_kha", "yield_ton_per_ha", "log_yield",
    "cropland_ratio", "fert", "irr", "flood", "drou_a", "flood_a",
    "ndvi_yearly", "ndvi_summer_peak",
    "lst_day_growing_mean_k", "lst_night_growing_mean_k",
    "annual_tmax", "annual_tmin", "annual_ppt", "annual_srad", "annual_pet",
    "max_month_prec_share",
]

PROVINCE_SHORT = {"黑龙江省": "黑龙江", "内蒙古自治区": "内蒙古"}


def short_province(p: str) -> str:
    if p in PROVINCE_SHORT:
        return PROVINCE_SHORT[p]
    for suffix in ("省", "市", "自治区"):
        if p.endswith(suffix):
            return p[: -len(suffix)]
    return p


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_panel() -> pd.DataFrame:
    df = pd.read_parquet(PANEL)
    missing = [c for c in CN_TO_EN if c not in df.columns]
    if missing:
        raise SystemExit(f"[FATAL] 面板缺少中文列: {missing}")
    df = df.rename(columns=CN_TO_EN)
    df["county_code"] = df["county_code"].astype(int)
    df["year"] = df["year"].astype(int)
    return df


def geo_name_counts() -> dict[str, int]:
    """天地图县级边界的原始县名重名统计（重名的只能用省份前缀消歧）。"""
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for f in geo["features"]:
        n = f["properties"]["name"]
        counts[n] = counts.get(n, 0) + 1
    return counts


def map_key_of(province: str, county: str, name_count: dict[str, int]) -> str:
    """面板县名 → 地图唯一键（与前端 geojson 的 properties.name 完全一致）。"""
    return f"{short_province(province)}{county}" if name_count.get(county, 0) > 1 else county


def build_web_map(panel_name_by_code: dict[int, str]) -> dict:
    """县级边界 → 前端地图资产。

    重写 properties.name 为**唯一键**：天地图原始县名在全国范围有重名
    （市辖区/桥西区/新华区/郊区/鼓楼区/市中区），而 ECharts 的 map series 只能按
    name 匹配，重名会导致一个值同时染两个县。重名的加省份前缀消歧。
    同时把坐标降到 4 位小数（约 11 m，县级面图足够），去掉落盘无用的字段。
    """
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    feats = geo["features"]

    name_count = geo_name_counts()

    out_feats = []
    for f in feats:
        p = f["properties"]
        adcode = int(p["adcode"])
        out_feats.append(
            {
                "type": "Feature",
                "properties": {
                    "name": map_key_of(p["province"], p["name"], name_count),
                    "adcode": adcode,
                    "county": p["name"],
                    "province": p["province"],
                    "has_panel": adcode in panel_name_by_code,
                },
                "geometry": _round_geometry(f["geometry"]),
            }
        )

    return {"type": "FeatureCollection", "features": out_feats}


def _round_geometry(geom: dict, ndigits: int = 4) -> dict:
    def r(coords):
        if isinstance(coords[0], (int, float)):
            return [round(coords[0], ndigits), round(coords[1], ndigits)]
        return [r(c) for c in coords]

    return {"type": geom["type"], "coordinates": r(geom["coordinates"])}


def write_db(df: pd.DataFrame, map_keys: dict[int, str], on_map: set[int]) -> dict:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()  # 全量重建，避免残留旧 schema

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    meta = (
        df.sort_values(["county_code", "year"])
        .drop_duplicates("county_code")
        .loc[:, ["county_code", "province", "city", "county", "lon", "lat"]]
    )
    meta["map_key"] = meta["county_code"].map(map_keys)
    meta["on_map"] = meta["county_code"].isin(on_map)
    panel_cols = ["county_code", "year"] + [
        c for c in CLIMATE_FEATURES + EXTRA_COLUMNS if c in df.columns and c != "year"
    ]

    cur.execute(
        """
        CREATE TABLE county_meta (
            county_code INTEGER PRIMARY KEY,
            province    TEXT NOT NULL,
            city        TEXT,
            county      TEXT NOT NULL,
            lon         REAL,
            lat         REAL,
            map_key     TEXT NOT NULL,
            on_map      INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE county_panel (
            county_code INTEGER NOT NULL REFERENCES county_meta(county_code),
            year        INTEGER NOT NULL,
            PRIMARY KEY (county_code, year)
        )
        """
    )
    cur.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    # county_panel 动态建列（特征口径由 CLIMATE_FEATURES / EXTRA_COLUMNS 决定）
    for c in panel_cols:
        if c in ("county_code", "year"):
            continue
        cur.execute(f'ALTER TABLE county_panel ADD COLUMN "{c}" REAL')

    meta.to_sql("county_meta", conn, if_exists="append", index=False)
    df.loc[:, panel_cols].to_sql("county_panel", conn, if_exists="append", index=False)
    cur.execute("CREATE INDEX idx_county_year ON county_panel(year)")

    rows = [
        ("schema_version", "1"),
        ("data_version", "v7-county"),
        ("source_parquet", str(PANEL.relative_to(PROJECT_ROOT)).replace("\\", "/")),
        ("source_parquet_md5", md5_of(PANEL)),
        ("geo_source", str(GEOJSON.relative_to(PROJECT_ROOT)).replace("\\", "/")),
        ("built_at", datetime.now(timezone.utc).isoformat()),
        ("n_rows", str(len(df))),
        ("n_counties", str(df["county_code"].nunique())),
        ("year_min", str(int(df["year"].min()))),
        ("year_max", str(int(df["year"].max()))),
        ("n_provinces", str(df["province"].nunique())),
        ("n_climate_features", str(len(CLIMATE_FEATURES))),
        ("climate_features", json.dumps(CLIMATE_FEATURES, ensure_ascii=False)),
    ]
    cur.executemany("INSERT INTO metadata VALUES (?, ?)", rows)
    conn.commit()
    conn.close()

    return {
        "rows": len(df),
        "counties": int(df["county_code"].nunique()),
        "columns": len(panel_cols),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="县级面板 → 站点 SQLite + 前端地图资产")
    ap.add_argument("--check-only", action="store_true", help="只做体检，不落盘")
    args = ap.parse_args()

    if not PANEL.exists():
        print(f"[FATAL] 面板不存在: {PANEL}")
        return 1

    df = load_panel()
    print(f"[面板] {PANEL.name}: {df.shape[0]} 行 × {df.shape[1]} 列")
    print(f"[面板] 县 {df['county_code'].nunique()} / 省 {df['province'].nunique()} / "
          f"年 {df['year'].min()}-{df['year'].max()}")

    # 体检：气候特征覆盖率
    for c in CLIMATE_FEATURES:
        if c not in df.columns:
            print(f"[FATAL] 缺气候特征列: {c}")
            return 1
    clim_ok = df[CLIMATE_FEATURES].notna().all(axis=1)
    print(f"[体检] 16 维气候齐备行: {int(clim_ok.sum())} / {len(df)} "
          f"({clim_ok.mean() * 100:.1f}%)")
    print(f"[体检] log_yield 非空: {int(df['log_yield'].notna().sum())} "
          f"({df['log_yield'].notna().mean() * 100:.1f}%)")
    print(f"[体检] 气候齐备且 log_yield 非空: {int((clim_ok & df['log_yield'].notna()).sum())}")

    if args.check_only:
        print("[check-only] 未落盘")
        return 0

    name_count = geo_name_counts()
    geo_codes = {
        int(f["properties"]["adcode"])
        for f in json.loads(GEOJSON.read_text(encoding="utf-8"))["features"]
    }
    map_keys = {
        int(r.county_code): map_key_of(r.province, r.county, name_count)
        for r in df.drop_duplicates("county_code").itertuples()
    }
    info = write_db(df, map_keys, geo_codes)
    print(f"[DB] {DB.relative_to(PROJECT_ROOT)} ← {info['rows']} 行 / "
          f"{info['counties']} 县 / {info['columns']} 列")
    print(f"[DB] 县级边界可渲染（on_map）：{len(set(map_keys) & geo_codes)} / {len(map_keys)} 县")

    panel_name_by_code = dict(zip(df["county_code"], df["county"]))
    web = build_web_map(panel_name_by_code)
    WEB_MAP.parent.mkdir(parents=True, exist_ok=True)
    WEB_MAP.write_text(
        json.dumps(web, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    matched = sum(1 for f in web["features"] if f["properties"]["has_panel"])
    print(f"[地图] {WEB_MAP.relative_to(PROJECT_ROOT)} ← {len(web['features'])} 面 / "
          f"{WEB_MAP.stat().st_size / 1024 / 1024:.2f} MB / 命中面板 {matched} 县")
    return 0


if __name__ == "__main__":
    sys.exit(main())
