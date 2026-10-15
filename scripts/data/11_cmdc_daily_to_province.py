#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""11：CMDC 全球地面日值（Asia）→ 10 主产省省级年度极端指数（1979-2023）。

数据源（本地 `data/` 下 UUID 命名的三个外层 zip 中的两个）
========================================================
  · `SURF_GLB_TEM_DAY_PROD_Asia_YYYY.zip` → `V12001` 日平均气温 (°C)
  · `SURF_GLB_PRE_DAY_V2_Asia_YYYY.zip`   → `V13011` 日累计降水量 (mm)
另一个 Africa 包与本任务无关。

坑（已实测）
============
1. 两个包的**列序不同**：气温是 ``V05001(纬) → V06001(经)``，
   降水是 ``V06001(经) → V05001(纬)``。一律**按列名取值**，禁止按位置取。
2. 外层 zip → 年内层 zip → 单个约 28 MB 的 GBK 编码 TSV（带表头行）。
3. ``V12001`` 是**日平均气温**。本地没有日最高/最低气温，所以 TX35、TX90p、
   DTR 这类标准 ETCCDI 温度指数**无法计算**；``days_tmean_ge30`` 是自定义
   阈值高温日，**不是标准 ETCCDI 指数**，对外引用时必须显式标注。
4. 生长季沿用 `scripts/data/v6_09_build_seasonal_features.py` 的定义：**4-9 月**。

站点归属
========
`data/raw/gis_province/counties_10provinces_GS2024.geojson` 点在多边形取
``province`` 列，**不用「最近省会」**那种近似。

输出
====
``data/interim/cmdc_province_yearly.parquet`` —— 省份 × 年份长表。

用法
====
    python scripts/data/11_cmdc_daily_to_province.py            # 全部 45 年
    python scripts/data/11_cmdc_daily_to_province.py --years 2019
    python scripts/data/11_cmdc_daily_to_province.py --qa 2019  # 只做质控体检
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.prepared import prep

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUT = DATA_DIR / "interim" / "cmdc_province_yearly.parquet"
COUNTIES = DATA_DIR / "raw" / "gis_province" / "counties_10provinces_GS2024.geojson"

TEN_PROVINCES = [
    "河北省", "吉林省", "黑龙江省", "江苏省", "安徽省",
    "山东省", "河南省", "湖北省", "湖南省", "四川省",
]
ALL_YEARS = list(range(1979, 2024))
GS_MONTHS = [4, 5, 6, 7, 8, 9]  # 生长季口径见 v6_09_build_seasonal_features.py
GDD_BASE = 10.0
DRY_THRESHOLD = 1.0  # 日降水 < 1.0 mm 记旱日（CDD 口径）
HOT_TMEAN = 30.0
# 物理合理值兜底：本产品在境外站存在哨兵/异常值（如单日 9000 mm），
# 10 主产省子集实测无 >300 mm 的记录，这里留出余量做统一裁剪并记录剔除数。
MAX_DAILY_PREC = 400.0
MAX_ABS_TMEAN = 60.0

TEMP_PREFIX = "SURF_GLB_TEM_DAY_PROD_Asia_"
PRE_PREFIX = "SURF_GLB_PRE_DAY_V2_Asia_"

TEMP_COLS = {"station": "V01301", "lat": "V05001", "lon": "V06001", "tmean": "V12001"}
PRE_COLS = {"station": "V01301", "lat": "V05001", "lon": "V06001", "prec": "V13011"}


def find_outer_zips() -> tuple[Path, Path]:
    """按内含成员名识别气温包与降水包（外层文件名是 UUID，不可依赖）。"""
    temp_zip = pre_zip = None
    for fp in sorted(DATA_DIR.glob("*.zip")):
        try:
            with zipfile.ZipFile(fp) as zf:
                names = zf.namelist()
        except zipfile.BadZipFile:
            continue
        if any(n.startswith(TEMP_PREFIX) for n in names):
            temp_zip = fp
        elif any(n.startswith(PRE_PREFIX) for n in names):
            pre_zip = fp
    if temp_zip is None or pre_zip is None:
        raise SystemExit(f"未能在 {DATA_DIR} 中同时找到气温包与降水包")
    return temp_zip, pre_zip


def year_member(outer: zipfile.ZipFile, prefix: str, year: int) -> str:
    for name in outer.namelist():
        if name.startswith(prefix) and name.endswith(f"_{year}.zip"):
            return name
    raise KeyError(f"{prefix}*_{year}.zip 不在包内")


def read_year(outer_path: Path, prefix: str, year: int, cols: dict, qcol: str | None = None) -> pd.DataFrame:
    """读一年的日值表：外层 zip → 年内层 zip → GBK TSV。按列名取列。"""
    usecols = ["V04001", "V04002", "V04003", *cols.values()]
    if qcol:
        usecols.append(qcol)
    with zipfile.ZipFile(outer_path) as outer:
        inner_bytes = outer.read(year_member(outer, prefix, year))
    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
        txt = next(n for n in inner.namelist() if n.endswith(".txt") and "readme" not in n.lower())
        with inner.open(txt) as stream:
            df = pd.read_csv(
                stream, sep="\t", encoding="gbk", usecols=usecols,
                dtype={cols["station"]: str}, low_memory=False,
            )
    df = df.rename(columns={v: k for k, v in cols.items()})
    df["date"] = pd.to_datetime(
        dict(year=df["V04001"], month=df["V04002"], day=df["V04003"]), errors="coerce"
    )
    df = df.dropna(subset=["date"])
    value_col = "tmean" if "tmean" in df.columns else "prec"
    limit = MAX_ABS_TMEAN if value_col == "tmean" else MAX_DAILY_PREC
    bad = df[value_col].abs() > limit
    if bad.any():
        logging.warning("%s %d: 剔除 %d 条超出物理合理值的记录（|%s| > %g）",
                        prefix.split("_")[2], year, int(bad.sum()), value_col, limit)
    df.loc[bad, value_col] = np.nan
    return df


class ProvinceResolver:
    """站点 → 省 的点在多边形解析（带缓存）。"""

    def __init__(self, geojson: Path) -> None:
        gdf = gpd.read_file(geojson).to_crs("EPSG:4326")
        gdf = gdf[gdf["province"].isin(TEN_PROVINCES)]
        # 县界/省界之间可能有缝，投影到米制缓冲 ~2 km 后再转回，避免边界站落空
        prov = gdf.dissolve(by="province").geometry.to_crs("EPSG:3857").buffer(2000).to_crs("EPSG:4326")
        self.geoms = {name: prep(geom) for name, geom in prov.items()}
        self.bounds = {name: geom.bounds for name, geom in prov.items()}
        self.cache: dict[str, str | None] = {}

    def resolve(self, station: str, lat: float, lon: float) -> str | None:
        if station in self.cache:
            return self.cache[station]
        hit = None
        for name, geom in self.geoms.items():
            minx, miny, maxx, maxy = self.bounds[name]
            if minx <= lon <= maxx and miny <= lat <= maxy and geom.contains(Point(lon, lat)):
                hit = name
                break
        self.cache[station] = hit
        return hit


def _max_run(mask: np.ndarray) -> int:
    """一维布尔数组里最长连续 True 的长度。"""
    if mask.size == 0 or not mask.any():
        return 0
    padded = np.concatenate(([0], mask.view(np.int8), [0]))
    idx = np.flatnonzero(np.diff(padded))
    return int((idx[1::2] - idx[::2]).max())


def _nanmean(a: np.ndarray, axis: int = 1) -> np.ndarray:
    """整段缺测的站会触发 RuntimeWarning，这里静默成 NaN。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a, axis=axis)


def temp_indices(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """站级年度气温指数：年均温 / 生长季均温 / 生长季积温 GDD10 / 自定义高温日数。"""
    wide = df.pivot_table(index="station", columns="date", values="tmean", aggfunc="mean").sort_index(axis=1)
    months = pd.DatetimeIndex(wide.columns).month.values
    vals = wide.to_numpy(dtype=float)
    gs = vals[:, np.isin(months, GS_MONTHS)]

    out = pd.DataFrame(index=wide.index)
    out["year"] = year
    out["tmean_annual"] = _nanmean(vals)
    out["gs_tmean"] = _nanmean(gs)
    out["gdd10"] = np.nansum(np.clip(gs - GDD_BASE, 0.0, None), axis=1)
    out["days_tmean_ge30"] = np.nansum(vals >= HOT_TMEAN, axis=1)
    out["n_days_temp"] = np.sum(~np.isnan(vals), axis=1)
    return out.reset_index()


def prec_indices(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """站级年度降水指数：年降水总量 / 分级强降水日数 / 最长连续无雨日 CDD。"""
    wide = df.pivot_table(index="station", columns="date", values="prec", aggfunc="mean")
    for day in pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D"):
        if day not in wide.columns:
            wide[day] = np.nan
    wide = wide.sort_index(axis=1)

    vals = wide.to_numpy(dtype=float)
    dry = np.nan_to_num(vals, nan=-1.0) < DRY_THRESHOLD  # 缺测不算旱日
    out = pd.DataFrame(index=wide.index)
    out["year"] = year
    out["prcptot_mm"] = np.nansum(vals, axis=1)
    out["r1mm_days"] = np.nansum(vals >= 1.0, axis=1)
    out["r25mm_days"] = np.nansum(vals >= 25.0, axis=1)
    out["r50mm_days"] = np.nansum(vals >= 50.0, axis=1)
    out["cdd_days"] = np.array([_max_run(row) for row in dry], dtype=float)
    out["n_days_prec"] = np.sum(~np.isnan(vals), axis=1)
    return out.reset_index()


def process_year(temp_zip: Path, pre_zip: Path, resolver: ProvinceResolver, year: int) -> pd.DataFrame:
    t = read_year(temp_zip, TEMP_PREFIX, year, TEMP_COLS)
    p = read_year(pre_zip, PRE_PREFIX, year, PRE_COLS)

    coord = t.groupby("station").agg(lat=("lat", "median"), lon=("lon", "median"))
    t = t[t["station"].isin(coord.index)]
    p = p[p["station"].isin(coord.index)]

    station = temp_indices(t, year).merge(prec_indices(p, year).drop(columns=["year"]), on="station", how="left")
    station["province"] = [
        resolver.resolve(s, coord.at[s, "lat"], coord.at[s, "lon"]) for s in station["station"]
    ]
    kept = station.dropna(subset=["province"])
    logging.info("  %d: 亚洲站 %d，落入 10 主产省 %d 站",
                 year, station["station"].nunique(), kept["station"].nunique())
    return kept


def aggregate(station_panel: pd.DataFrame) -> pd.DataFrame:
    """站级 → 省级：各指数取站间均值，另记站数与有效站日数。"""
    idx_cols = ["tmean_annual", "gs_tmean", "gdd10", "days_tmean_ge30",
                "prcptot_mm", "r1mm_days", "r25mm_days", "r50mm_days", "cdd_days"]
    agg = station_panel.groupby(["province", "year"]).agg(
        n_stations=("station", "nunique"),
        n_station_days_temp=("n_days_temp", "sum"),
        n_station_days_prec=("n_days_prec", "sum"),
        **{c: (c, "mean") for c in idx_cols},
    ).reset_index()
    return agg.sort_values(["province", "year"]).reset_index(drop=True)


def qa_one_year(temp_zip: Path, pre_zip: Path, year: int) -> None:
    """单年质控体检：行数、站数、日期范围、质控码分布、缺测率。"""
    for label, outer, prefix, cols, qcol in (
        ("气温", temp_zip, TEMP_PREFIX, TEMP_COLS, "Q12001"),
        ("降水", pre_zip, PRE_PREFIX, PRE_COLS, "Q13011"),
    ):
        df = read_year(outer, prefix, year, cols, qcol)
        val = "tmean" if label == "气温" else "prec"  # read_year 已重命名为规范列名
        print(f"[{label}] {year}｜行数 {len(df):,}｜站数 {df['station'].nunique():,}｜"
              f"日期 {df['date'].min().date()} ~ {df['date'].max().date()}")
        print(f"  Q 质控码分布: {df[qcol].value_counts(dropna=False).head(8).to_dict()}")
        print(f"  {val} 缺测率: {df[val].isna().mean():.4%}｜"
              f"分位 {df[val].quantile([0.01, 0.5, 0.99]).round(2).to_dict()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="CMDC 日值 → 省级年度极端指数")
    parser.add_argument("--years", type=int, nargs="*", default=ALL_YEARS)
    parser.add_argument("--qa", type=int, help="只对指定年份做质控体检，不产出面板")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover
        pass

    temp_zip, pre_zip = find_outer_zips()
    print(f"气温包: {temp_zip.name}\n降水包: {pre_zip.name}")
    if args.qa:
        qa_one_year(temp_zip, pre_zip, args.qa)
        return 0

    resolver = ProvinceResolver(COUNTIES)
    frames = [aggregate(process_year(temp_zip, pre_zip, resolver, y)) for y in args.years]
    out = pd.concat(frames, ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    logging.info("写入 %s（%d 行，%d 省 × %d 年）",
                 args.out, len(out), out["province"].nunique(), out["year"].nunique())
    print(out.head(6).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
