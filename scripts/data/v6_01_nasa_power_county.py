#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 1：县级年度气候面板（ERA5，经 Open-Meteo archive API，多坐标点批量）。

对 1,196 个县（有 lon/lat 的），用 county seat 坐标拉取 2012-2023 逐日气候，
聚合为年值。数据源为 ERA5 reanalysis（Open-Meteo 免费 API）。

为什么不用 NASA POWER：power.larc.nasa.gov 在国内网络不可达（v4/v5 曾在
Linux 服务器抓取；本机 curl HTTP 000）。Open-Meteo 可直连，且提供
sunshine_duration（日照时数）——v4 特征里的 sun 正是日照时数。

批量策略：archive 端点支持逗号分隔多坐标（bulk-api 域名被墙不可用），
每请求 25 县 → 共 ~48 请求。匿名 keyless 限流约 3-5 次/分钟，
单点逐县跑 1,196 次不可行，批量化后分钟级完成。

变量映射（对齐 v4 nasa_power_annual.csv 口径）：
  temperature_2m_mean (°C)  → temp   = 年均温
  precipitation_sum (mm)    → prec   = 年降水量
  sunshine_duration (s)     → sun    = 年日照时数（s→h）

输出：
  data/interim/era5_county_yearly_v6.parquet (1,196 县 × 12 年)
  断点续传: --resume data/logs/v6_era5_checkpoint.csv

用法：
  python scripts/data/v6_01_nasa_power_county.py            # 全量
  python scripts/data/v6_01_nasa_power_county.py --test     # 1 批试跑
  python scripts/data/v6_01_nasa_power_county.py --resume data/logs/v6_era5_checkpoint.csv
"""
import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "interim" / "era5_county_yearly_v6.parquet"
CHECKPOINT = PROJECT_ROOT / "data" / "logs" / "v6_era5_checkpoint.csv"

API = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = "temperature_2m_mean,precipitation_sum,sunshine_duration"
START = "2012-01-01"
END = "2023-12-31"
MIN_DAYS = 330  # 年有效天数下限，不足则当年置 None
BATCH = 25      # 每请求县数（响应 ~3.4MB）
BATCH_DELAY = 2.0  # 批间间隔（约 30/min，安全）
TIMEOUT = 180
MAX_RETRY = 4
SESSION = requests.Session()  # keep-alive


def fetch_batch(pts: pd.DataFrame) -> dict[int, dict[int, dict[str, float]]]:
    """拉取一批县的 2012-2023 逐日值，聚合为 {区县代码: {year: {temp, prec, sun}}}。"""
    params = {
        "latitude": ",".join(f"{v:.4f}" for v in pts["lat"]),
        "longitude": ",".join(f"{v:.4f}" for v in pts["lon"]),
        "start_date": START,
        "end_date": END,
        "daily": DAILY_VARS,
        "timezone": "GMT",
    }
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = SESSION.get(API, params=params, timeout=TIMEOUT)
            if resp.status_code == 429:
                wait = 20 * attempt
                logging.warning("429 限流, 退避 %ds (attempt %d/%d)", wait, attempt, MAX_RETRY)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return {}
            out: dict[int, dict[int, dict[str, float]]] = {}
            for j, loc in enumerate(data):
                d = loc.get("daily")
                if not d or not d.get("time"):
                    continue
                cid = int(pts.iloc[j]["区县代码"])
                times = d["time"]
                t2m = np.array(d["temperature_2m_mean"], dtype=float)
                prec = np.array(d["precipitation_sum"], dtype=float)
                sun = np.array(d["sunshine_duration"], dtype=float)
                years = np.array([int(t[:4]) for t in times])

                yearly: dict[int, dict[str, float]] = {}
                for y in range(2012, 2024):
                    mask = years == y
                    if mask.sum() < MIN_DAYS:
                        continue
                    t_valid = t2m[mask]
                    if np.isnan(t_valid).mean() > 0.1:
                        continue
                    yearly[y] = {
                        "temp": round(float(np.nanmean(t_valid)), 4),
                        "prec": round(float(np.nansum(prec[mask])), 2),
                        "sun": round(float(np.nansum(sun[mask])) / 3600.0, 1),  # s → h
                    }
                out[cid] = yearly
            return out
        except requests.RequestException as e:
            if attempt < MAX_RETRY:
                time.sleep(10 * attempt)
            else:
                logging.warning("batch fetch failed: %s", e)
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ERA5(Open-Meteo 批量) → 县级年度气候 (v6)")
    parser.add_argument("--test", action="store_true", help="仅 1 批试跑")
    parser.add_argument("--resume", type=str, help="从 checkpoint CSV 恢复")
    parser.add_argument("--delay", type=float, default=BATCH_DELAY, help="批间间隔秒")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    df = pd.read_parquet(PANEL)
    pts = df[["区县代码", "省份", "城市", "区县", "lon", "lat"]].dropna(subset=["lon", "lat"])
    pts = pts.drop_duplicates("区县代码").reset_index(drop=True)
    logging.info("县级气候点: %d 个 (缺失经纬度 %d)", len(pts), df["lon"].isna().sum())

    done: set[int] = set()
    if args.resume:
        ckpt = pd.read_csv(args.resume)
        done = set(ckpt["区县代码"].astype(int).unique())
        logging.info("断点恢复: 已完成 %d 县", len(done))

    if args.test:
        batches = [pts.head(BATCH)]
    else:
        todo = pts[~pts["区县代码"].isin(done)].reset_index(drop=True)
        batches = [todo.iloc[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    logging.info("待处理 %d 县, 共 %d 批 (每批 %d)", sum(len(b) for b in batches), len(batches), BATCH)

    all_rows: list[dict] = []
    for bi, batch in enumerate(batches):
        result = fetch_batch(batch)
        for cid, yearly in result.items():
            meta = batch[batch["区县代码"] == cid].iloc[0]
            for year, agg in yearly.items():
                all_rows.append({
                    "区县代码": cid,
                    "province": meta["省份"], "city": meta["城市"], "county": meta["区县"],
                    "year": year, **agg,
                })
        # checkpoint 每批落盘
        pd.DataFrame([{"区县代码": int(c)} for c in batch["区县代码"]]).to_csv(
            CHECKPOINT, index=False, mode="a" if bi > 0 else "w", header=bi == 0)
        if (bi + 1) % 5 == 0:
            logging.info("batch %d/%d 完成 (累计 %d 行)", bi + 1, len(batches), len(all_rows))
        time.sleep(args.delay)

    out = pd.DataFrame(all_rows)
    if not out.empty:
        out = out.drop_duplicates(["区县代码", "year"]).sort_values(["区县代码", "year"]).reset_index(drop=True)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(OUT_PATH, index=False)
        logging.info("✅ 写入 %s (%d 行, %d 县)", OUT_PATH, len(out), out["区县代码"].nunique())
    else:
        logging.warning("无数据产出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
