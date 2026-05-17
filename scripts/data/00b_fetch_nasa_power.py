"""NASA POWER 拉气象（温度/降水/日照）—— 重建论文面板的 Phase 2。

来源：https://power.larc.nasa.gov/api/temporal/daily/point
无需账号、无 ToS 限制（科研使用）。

输入：data/interim/province_centroids.csv（31 省 representative_point）
输出：data/interim/nasa_power_daily/<province_code>.csv （每省一份 daily）
      data/interim/nasa_power_annual.csv（31×13 年汇总）

变量映射：
  T2M (°C, 日均温) → temp (年均温 °C)
  PRECTOTCORR (mm/day) → prec (年降水量 mm)
  ALLSKY_SFC_SW_DWN / CLRSKY_SFC_SW_DWN → sun (年日照时数估算, hours)

⚠️  日照时数说明：POWER 不直接给"日照时数"，本脚本用
  sun_hours_annual ≈ 4380 × (ALLSKY / CLRSKY 年均)
其中 4380 = 12h × 365 是理论年日照上限。这是 Angstrom-Prescott 反推近似，
与气象站实测可能差 ±10%。论文 panel 字段保持 `sun`，但 docs/09 数据集说明
要标注该列为「重建估算」，不是站点实测。

CLI:
    python scripts/data/00b_fetch_nasa_power.py                       # 全 31 省 × 2011-2023
    python scripts/data/00b_fetch_nasa_power.py --province 410000     # 单省（河南）测试
    python scripts/data/00b_fetch_nasa_power.py --years 2022-2022     # 单年
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CENTROIDS = PROJECT_ROOT / "data" / "interim" / "province_centroids.csv"
DEFAULT_DAILY_DIR = PROJECT_ROOT / "data" / "interim" / "nasa_power_daily"
DEFAULT_ANNUAL = PROJECT_ROOT / "data" / "interim" / "nasa_power_annual.csv"

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS_LIST = ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "CLRSKY_SFC_SW_DWN"]
COMMUNITY = "AG"
TIMEOUT = 180  # POWER 偶尔慢


def fetch_point(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """拉一个点 daily JSON → DataFrame。带 1 次重试。"""
    params = {
        "parameters": ",".join(PARAMS_LIST),
        "community": COMMUNITY,
        "longitude": f"{lon:.4f}",
        "latitude": f"{lat:.4f}",
        "start": start,
        "end": end,
        "format": "JSON",
    }
    for attempt in (1, 2):
        try:
            r = requests.get(POWER_URL, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            payload = r.json()
            break
        except (requests.RequestException, json.JSONDecodeError) as e:
            if attempt == 2:
                raise
            logging.warning("第 %d 次失败 (%s)，5 秒后重试", attempt, e)
            time.sleep(5)

    parameter = payload.get("properties", {}).get("parameter", {})
    if not parameter:
        raise RuntimeError(f"POWER 返回空 parameter，全文 = {json.dumps(payload)[:500]}")
    dates = sorted(next(iter(parameter.values())).keys())
    rows = []
    for d in dates:
        row = {"date": d}
        for p in PARAMS_LIST:
            v = parameter.get(p, {}).get(d)
            # POWER 缺测用 -999
            row[p] = None if v is None or v < -990 else v
        rows.append(row)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    return df


def aggregate_annual(daily: pd.DataFrame, province_code: str, province: str) -> pd.DataFrame:
    daily = daily.copy()
    daily["year"] = daily["date"].dt.year
    annual = daily.groupby("year").agg(
        temp=("T2M", "mean"),
        prec=("PRECTOTCORR", "sum"),
        sw_actual=("ALLSKY_SFC_SW_DWN", "mean"),
        sw_clear=("CLRSKY_SFC_SW_DWN", "mean"),
        days=("date", "count"),
    ).reset_index()

    # 日照时数近似（小时）：4380h 理论年上限 × actual/clear 比
    annual["sun"] = 4380.0 * annual["sw_actual"] / annual["sw_clear"]
    annual["province_code"] = province_code
    annual["province"] = province
    return annual[["province_code", "province", "year", "temp", "prec", "sun", "sw_actual", "sw_clear", "days"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NASA POWER 拉 31 省气象")
    parser.add_argument("--centroids", type=Path, default=DEFAULT_CENTROIDS)
    parser.add_argument("--daily-dir", type=Path, default=DEFAULT_DAILY_DIR)
    parser.add_argument("--annual", type=Path, default=DEFAULT_ANNUAL)
    parser.add_argument("--province", type=str, help="只跑指定 province_code，例 410000")
    parser.add_argument("--years", type=str, default="2011-2023", help="年份范围 START-END")
    parser.add_argument("--sleep", type=float, default=0.5, help="每次请求间隔（避免 NASA 限速）")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    centroids = pd.read_csv(args.centroids, dtype={"province_code": str})
    if args.province:
        centroids = centroids[centroids["province_code"] == args.province]
        if centroids.empty:
            logging.error("找不到 province_code=%s", args.province)
            return 1

    lo, hi = args.years.split("-", 1)
    start = f"{lo}0101"
    end = f"{hi}1231"

    args.daily_dir.mkdir(parents=True, exist_ok=True)
    annual_frames: list[pd.DataFrame] = []

    bar = tqdm(centroids.itertuples(index=False), total=len(centroids), desc="省份")
    for row in bar:
        bar.set_postfix_str(row.province)
        daily_path = args.daily_dir / f"{row.province_code}.csv"

        if daily_path.exists():
            logging.info("缓存命中 %s，跳过下载", daily_path.name)
            daily = pd.read_csv(daily_path, parse_dates=["date"])
        else:
            logging.info("拉 %s (%.2f, %.2f) %s..%s", row.province, row.lat, row.lon, start, end)
            daily = fetch_point(row.lat, row.lon, start, end)
            daily.to_csv(daily_path, index=False)
            time.sleep(args.sleep)

        annual = aggregate_annual(daily, row.province_code, row.province)
        annual_frames.append(annual)

    full_annual = pd.concat(annual_frames, ignore_index=True).sort_values(["province_code", "year"])
    args.annual.parent.mkdir(parents=True, exist_ok=True)
    full_annual.to_csv(args.annual, index=False)
    logging.info("✅ 全部完成，annual 表 %d 行 → %s", len(full_annual), args.annual)
    print(full_annual.head(15).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
