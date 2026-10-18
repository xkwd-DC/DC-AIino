#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11 Step 1：构建 M03「玉米长势」页签的县级基线参数。

输入
====
- backend/data/county.db（county_meta + county_panel，1,199 县 × 2012–2023）
- data/interim/nasapower_county_daily_extremes.parquet（逐日派生高温日数）

输出
====
- backend/data/maize_growth_baseline.json

口径
====
- 只保留玉米主产区：东北春玉米（黑、吉）、黄淮海夏玉米（冀、鲁、豫、
  苏北、皖北，纬度 ≥ 32.5）、西南春玉米（川）。
- 湘、鄂为稻区，不进入玉米模拟；苏皖南部同理。
- 基线值取 2012–2023 年均值；heat_p90 留作参考，当前热害按全季
  ≥35℃ 日数的 1/4 折算到抽雄吐丝期（基线在相对 GSI 里约掉）。
- 本文件只提供统计基线，不是 DSSAT 机理模型参数。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "backend" / "data" / "county.db"
HEAT = ROOT / "data" / "interim" / "nasapower_county_daily_extremes.parquet"
OUT = ROOT / "backend" / "data" / "maize_growth_baseline.json"

# 玉米参数按种植制度分三档。GDD 单位为 ℃·d，season_days 用于把 ΔT 折算成积温增量。
ZONES = {
    "NE": {
        "key": "NE",
        "name": "东北春玉米",
        "req_gdd": 1250,
        "season_days": 153,
        "sowing": "4/25–5/10",
        "kc": 1.15,
        "pet_fraction": 0.95,
    },
    "HHH": {
        "key": "HHH",
        "name": "黄淮海夏玉米",
        "req_gdd": 2350,
        "season_days": 122,
        "sowing": "6/10–6/25",
        "kc": 1.15,
        "pet_fraction": 0.67,
    },
    "SW": {
        "key": "SW",
        "name": "西南春玉米",
        "req_gdd": 2350,
        "season_days": 153,
        "sowing": "3/20–4/15",
        "kc": 1.15,
        "pet_fraction": 0.95,
    },
}


def assign_zone(province: str, lat: float | None) -> str | None:
    if province in ("黑龙江省", "吉林省"):
        return "NE"
    if province in ("河北省", "山东省", "河南省"):
        return "HHH"
    if province == "四川省":
        return "SW"
    if province in ("江苏省", "安徽省") and lat is not None and lat >= 32.5:
        return "HHH"
    return None


def baseline_gsi(gdd: float, ppt: float, pet: float, irr: float, zone: dict) -> float:
    f_gdd = min(1.0, max(0.0, gdd) / zone["req_gdd"])
    etc = zone["kc"] * pet
    supply = irr * etc + (1.0 - irr) * 0.75 * ppt
    f_water = 1.0 - 0.6 * max(0.0, (etc - supply) / etc) if etc > 0 else 0.25
    f_water = min(1.0, max(0.25, f_water))
    return 100.0 * min(f_gdd, f_water)


def main() -> None:
    conn = sqlite3.connect(DB)
    meta = pd.read_sql("select county_code, province, city, county, lon, lat from county_meta", conn)
    panel = pd.read_sql(
        """
        select county_code, year, gdd10, gs_ppt, gs_pet, gs_tmax_mean,
               spei_growing_season_mean, irr, ndvi_summer_peak
        from county_panel
        """,
        conn,
    )
    conn.close()

    agg = (
        panel.groupby("county_code")
        .agg(
            years=("year", "nunique"),
            gdd=("gdd10", "mean"),
            ppt=("gs_ppt", "mean"),
            pet=("gs_pet", "mean"),
            tmax=("gs_tmax_mean", "mean"),
            spei=("spei_growing_season_mean", "mean"),
            irr=("irr", "mean"),
            ndvi=("ndvi_summer_peak", "mean"),
        )
        .reset_index()
    )
    agg["irr"] = (agg["irr"] / 100.0).clip(0.0, 1.0)

    heat = pd.read_parquet(HEAT, columns=["county_code", "np_heat_days35"])
    heat_agg = (
        heat.groupby("county_code")["np_heat_days35"]
        .agg(heat_mean="mean", heat_p90=lambda s: s.quantile(0.9))
        .reset_index()
    )

    df = meta.merge(agg, on="county_code", how="inner").merge(heat_agg, on="county_code", how="left")
    df["zone"] = [assign_zone(p, lat) for p, lat in zip(df["province"], df["lat"])]
    df = df[df["zone"].notna()].copy()
    # 剔除高寒山区：按区分设 GDD 下限（本数据集为 4–9 月月均口径，
    # 东北 1200–1400 是常态，不能套文献全生育期 2500+ 的绝对值）。
    zone_min_gdd = {"NE": 1000.0, "HHH": 1900.0, "SW": 1800.0}
    df = df[df.apply(lambda r: r["gdd"] >= zone_min_gdd[r["zone"]], axis=1)].copy()
    df["heat_mean"] = df["heat_mean"].fillna(0.0)
    df["heat_p90"] = df["heat_p90"].fillna(df["heat_mean"])
    df["baseline_gsi"] = [
        baseline_gsi(g, p, e, i, ZONES[z])
        for g, p, e, i, z in zip(df["gdd"], df["ppt"], df["pet"], df["irr"], df["zone"])
    ]

    rows = []
    for r in df.itertuples(index=False):
        rows.append(
            {
                "code": int(r.county_code),
                "name": r.county,
                "province": r.province,
                "city": r.city,
                "lon": round(float(r.lon), 4) if pd.notna(r.lon) else None,
                "lat": round(float(r.lat), 4) if pd.notna(r.lat) else None,
                "zone": r.zone,
                "gdd": round(float(r.gdd), 1),
                "ppt": round(float(r.ppt), 1),
                "pet": round(float(r.pet), 1),
                "tmax": round(float(r.tmax), 2),
                "spei": round(float(r.spei), 3),
                "irr": round(float(r.irr), 4),
                "ndvi": round(float(r.ndvi), 4),
                "heat_mean": round(float(r.heat_mean), 2),
                "heat_p90": round(float(r.heat_p90), 2),
                "baseline_gsi": round(float(r.baseline_gsi), 1),
            }
        )

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "crop": "玉米",
            "years": [int(panel["year"].min()), int(panel["year"].max())],
            "county_count": len(rows),
            "source": "county.db + nasapower_county_daily_extremes.parquet",
            "note": (
                "统计基线，非 DSSAT 机理模型；仅覆盖玉米主产区。"
                "gdd 为 4–9 月 ≥10℃ 积温（TerraClimate 月均口径），"
                "分区阈值按本数据集校准，不与文献全生育期 GDD 直接比较。"
            ),
        },
        "zones": list(ZONES.values()),
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"写出 {OUT} — {len(rows)} 县")
    print(df.groupby("zone").size().to_string())
    print(
        "baseline_gsi:",
        round(df["baseline_gsi"].min(), 1),
        "-",
        round(df["baseline_gsi"].max(), 1),
        "| 中位",
        round(df["baseline_gsi"].median(), 1),
    )


if __name__ == "__main__":
    main()
