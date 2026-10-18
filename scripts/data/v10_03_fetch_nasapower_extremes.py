#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v10 Step 3（NASA POWER 版）：1,199 县日值 → 极端指数。

为什么换 NASA POWER：
  Open-Meteo 免费 archive 端点对 25 县 × 12 年的大请求连续 429；
  NASA POWER point API 单点 7 秒、215 KB，实测可达。1,196 县用 6 线程
  预计 20–30 分钟，且有断点续传。

变量：
  T2M_MAX / T2M_MIN / PRECTOTCORR（°C / °C / mm/day）

指数（生长季 4–9 月）：
  np_tmax_mean_gs / np_tmax_max_gs / np_heat_days35
  np_tmin_min_gs / np_frost_days
  np_prec_sum_gs / np_wet_days / np_rainstorm_days / np_cdd_max
  np_gdd10 / np_prec_p95 / np_r95p_days

用法：
  python scripts/data/v10_03_fetch_nasapower_extremes.py --test
  python scripts/data/v10_03_fetch_nasapower_extremes.py --workers 6
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
CENTROIDS = ROOT / "data" / "interim" / "county_centroids_1199.csv"
OUT = ROOT / "data" / "interim" / "nasapower_county_daily_extremes.parquet"
CHECKPOINT = ROOT / "data" / "logs" / "v10_nasapower_checkpoint.csv"

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "T2M_MAX,T2M_MIN,PRECTOTCORR"
START = "20120101"
END = "20231231"
TIMEOUT = 90
MAX_RETRY = 3


def _cdd_max(prec: np.ndarray, threshold: float = 1.0) -> int:
    best = cur = 0
    for v in prec:
        if np.isfinite(v) and v < threshold:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def fetch_one(row, session: requests.Session) -> list[dict] | None:
    params = {
        "parameters": PARAMS,
        "community": "AG",
        "longitude": f"{row.lon:.4f}",
        "latitude": f"{row.lat:.4f}",
        "start": START,
        "end": END,
        "format": "JSON",
    }
    for attempt in range(1, MAX_RETRY + 1):
        try:
            r = session.get(URL, params=params, timeout=TIMEOUT)
            if r.status_code in (429, 503):
                time.sleep(20 * attempt)
                continue
            r.raise_for_status()
            p = r.json()["properties"]["parameter"]
            dates = sorted(p["T2M_MAX"].keys())
            tmax = np.array([p["T2M_MAX"][d] for d in dates], dtype=float)
            tmin = np.array([p["T2M_MIN"][d] for d in dates], dtype=float)
            prec = np.array([p["PRECTOTCORR"][d] for d in dates], dtype=float)
            tmax[tmax <= -900] = np.nan
            tmin[tmin <= -900] = np.nan
            prec[prec <= -900] = np.nan
            years = np.array([int(d[:4]) for d in dates])
            months = np.array([int(d[4:6]) for d in dates])

            rows = []
            for y in range(2012, 2024):
                ym = years == y
                if ym.sum() < 330:
                    continue
                gs = ym & (months >= 4) & (months <= 9)
                tx, tn, pr = tmax[gs], tmin[gs], prec[gs]
                ok = np.isfinite(tx) & np.isfinite(tn) & np.isfinite(pr)
                if ok.sum() < 150:
                    continue
                tx, tn, pr = tx[ok], tn[ok], pr[ok]
                wet = pr[pr >= 1.0]
                p95 = float(np.quantile(wet, 0.95)) if len(wet) else np.nan
                tmean = (tx + tn) / 2.0
                frost = int((tmin[ym & np.isfinite(tmin)] < 0).sum())
                rows.append({
                    "county_code": int(row.county_code),
                    "year": y,
                    "np_tmax_mean_gs": round(float(np.mean(tx)), 4),
                    "np_tmax_max_gs": round(float(np.max(tx)), 4),
                    "np_heat_days35": int((tx >= 35).sum()),
                    "np_tmin_min_gs": round(float(np.min(tn)), 4),
                    "np_frost_days": frost,
                    "np_prec_sum_gs": round(float(np.sum(pr)), 4),
                    "np_wet_days": int((pr >= 1.0).sum()),
                    "np_rainstorm_days": int((pr >= 50.0).sum()),
                    "np_cdd_max": _cdd_max(pr),
                    "np_gdd10": round(float(np.maximum(tmean - 10.0, 0.0).sum()), 4),
                    "np_prec_p95": round(p95, 4) if np.isfinite(p95) else np.nan,
                    "np_r95p_days": int((wet > p95).sum()) if np.isfinite(p95) else 0,
                })
            return rows
        except Exception as e:
            if attempt == MAX_RETRY:
                logging.warning("county %s 失败: %s", row.county_code, e)
                return None
            time.sleep(5 * attempt)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--test", type=int, default=0, help="只跑前 N 个县")
    ap.add_argument("--resume", type=Path, default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    pts = pd.read_csv(CENTROIDS).dropna(subset=["lon", "lat"]).drop_duplicates("county_code").reset_index(drop=True)
    done: set[int] = set()
    if args.resume and args.resume.exists():
        done = set(pd.read_csv(args.resume)["county_code"].astype(int).unique())
        logging.info("断点恢复：已完成 %d 县", len(done))
    todo = pts[~pts["county_code"].isin(done)].reset_index(drop=True)
    if args.test:
        todo = todo.head(args.test)
    logging.info("待处理 %d 县，%d 线程", len(todo), args.workers)

    lock = threading.Lock()
    all_rows: list[dict] = []
    if args.resume and OUT.exists():
        all_rows = pd.read_parquet(OUT).to_dict("records")
        logging.info("载入已有结果 %d 行", len(all_rows))

    session = requests.Session()
    finished = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_one, row, session): row for row in todo.itertuples()}
        for fut in as_completed(futures):
            row = futures[fut]
            rows = fut.result()
            finished += 1
            if rows:
                with lock:
                    all_rows.extend(rows)
            if finished % 20 == 0 or finished == len(todo):
                with lock:
                    df = pd.DataFrame(all_rows).drop_duplicates(["county_code", "year"])
                    df.to_parquet(OUT, index=False)
                    pd.DataFrame({"county_code": sorted(set(df["county_code"].astype(int)))}).to_csv(
                        CHECKPOINT, index=False
                    )
                logging.info("完成 %d/%d 县，累计 %d 行", finished, len(todo), len(df))

    df = pd.DataFrame(all_rows).drop_duplicates(["county_code", "year"]).sort_values(["county_code", "year"])
    df.to_parquet(OUT, index=False)
    pd.DataFrame({"county_code": sorted(df["county_code"].astype(int).unique())}).to_csv(CHECKPOINT, index=False)
    print(f"✅ {OUT} | {len(df)} 行 | {df['county_code'].nunique()} 县 | {df['year'].min()}-{df['year'].max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
