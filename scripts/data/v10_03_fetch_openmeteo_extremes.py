#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v10 Step 3（快速版）：Open-Meteo 日值 → 1,199 县极端指数。

为什么不用 ERA5-Land/CDS：
  10 省 × 6 个月 × 3 小时 × 2 变量的 NetCDF 包 432 MB，本机 CDS 下载约 10 KB/s，
  要十几小时。Open-Meteo archive API 支持一次 25 个县批量返回 2012–2023 逐日
  Tmax/Tmin/降水，48 个请求即可，分钟级完成。

补的变量：
  om_tmax_mean_gs / om_tmax_max_gs / om_heat_days35
  om_tmin_min_gs / om_frost_days
  om_prec_sum_gs / om_wet_days / om_rainstorm_days / om_cdd_max
  om_gdd10 / om_prec_p95 / om_r95p_days

口径：
  - 县治点最近格点（Open-Meteo 0.1° 左右）
  - 生长季 4–9 月（与现有 CLIMG 一致）
  - 日值按 Asia/Shanghai 本地日

用法：
  python scripts/data/v10_03_fetch_openmeteo_extremes.py --test
  python scripts/data/v10_03_fetch_openmeteo_extremes.py
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CENTROIDS = PROJECT_ROOT / "data" / "interim" / "county_centroids_1199.csv"
OUT = PROJECT_ROOT / "data" / "interim" / "openmeteo_county_daily_extremes.parquet"
CHECKPOINT = PROJECT_ROOT / "data" / "logs" / "v10_openmeteo_checkpoint.csv"

API = "https://archive-api.open-meteo.com/v1/archive"
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum"
START = "2012-01-01"
END = "2023-12-31"
BATCH = 25
TIMEOUT = 180
MAX_RETRY = 4


def _cdd_max(prec: np.ndarray, threshold: float = 1.0) -> int:
    best = cur = 0
    for v in prec:
        if np.isfinite(v) and v < threshold:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def fetch_batch(pts: pd.DataFrame, session: requests.Session) -> list[dict]:
    params = {
        "latitude": ",".join(f"{v:.4f}" for v in pts["lat"]),
        "longitude": ",".join(f"{v:.4f}" for v in pts["lon"]),
        "start_date": START,
        "end_date": END,
        "daily": DAILY,
        "timezone": "Asia/Shanghai",
    }
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = session.get(API, params=params, timeout=TIMEOUT)
            if resp.status_code == 429:
                wait = 20 * attempt
                logging.warning("429 限流，退避 %ds (%d/%d)", wait, attempt, MAX_RETRY)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                logging.warning("返回不是 list，跳过本批")
                return []
            rows: list[dict] = []
            for j, loc in enumerate(data):
                d = loc.get("daily") or {}
                if not d.get("time"):
                    continue
                times = np.array(d["time"])
                years = np.array([int(t[:4]) for t in times])
                months = np.array([int(t[5:7]) for t in times])
                tmax = np.array(d["temperature_2m_max"], dtype=float)
                tmin = np.array(d["temperature_2m_min"], dtype=float)
                prec = np.array(d["precipitation_sum"], dtype=float)
                cid = int(pts.iloc[j]["county_code"])

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
                    gdd = float(np.maximum(tmean - 10.0, 0.0).sum())
                    frost = int((tmin[ym & np.isfinite(tmin)] < 0).sum())
                    rows.append({
                        "county_code": cid,
                        "year": y,
                        "om_tmax_mean_gs": round(float(np.mean(tx)), 4),
                        "om_tmax_max_gs": round(float(np.max(tx)), 4),
                        "om_heat_days35": int((tx >= 35).sum()),
                        "om_tmin_min_gs": round(float(np.min(tn)), 4),
                        "om_frost_days": frost,
                        "om_prec_sum_gs": round(float(np.sum(pr)), 4),
                        "om_wet_days": int((pr >= 1.0).sum()),
                        "om_rainstorm_days": int((pr >= 50.0).sum()),
                        "om_cdd_max": _cdd_max(pr),
                        "om_gdd10": round(gdd, 4),
                        "om_prec_p95": round(p95, 4) if np.isfinite(p95) else np.nan,
                        "om_r95p_days": int((wet > p95).sum()) if np.isfinite(p95) else 0,
                    })
            return rows
        except Exception as e:
            logging.warning("请求失败 (%d/%d): %s", attempt, MAX_RETRY, e)
            time.sleep(10 * attempt)
    logging.error("本批重试耗尽，跳过")
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="只跑第一批 25 县")
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--resume", type=Path, default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    pts = pd.read_csv(CENTROIDS)
    pts = pts.dropna(subset=["lon", "lat"]).drop_duplicates("county_code").reset_index(drop=True)
    logging.info("县级点: %d", len(pts))

    done: set[int] = set()
    if args.resume and args.resume.exists():
        done = set(pd.read_csv(args.resume)["county_code"].astype(int).unique())
        logging.info("断点恢复: 已完成 %d 县", len(done))

    todo = pts[~pts["county_code"].isin(done)].reset_index(drop=True)
    batches = [todo.iloc[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    if args.test:
        batches = batches[:1]
    logging.info("待处理 %d 县，%d 批", sum(len(b) for b in batches), len(batches))

    session = requests.Session()
    all_rows: list[dict] = []
    if args.resume and OUT.exists():
        all_rows = pd.read_parquet(OUT).to_dict("records")
        logging.info("已载入现有结果 %d 行", len(all_rows))
    for bi, batch in enumerate(batches):
        rows = fetch_batch(batch, session)
        all_rows.extend(rows)
        pd.DataFrame({"county_code": batch["county_code"].astype(int)}).to_csv(
            CHECKPOINT, index=False, mode="a" if bi > 0 else "w", header=bi == 0
        )
        logging.info("batch %d/%d：本批 %d 县年，累计 %d 行", bi + 1, len(batches), len(rows), len(all_rows))
        if all_rows:
            pd.DataFrame(all_rows).drop_duplicates(["county_code", "year"]).to_parquet(OUT, index=False)
        time.sleep(args.delay)

    if all_rows:
        out = pd.DataFrame(all_rows).drop_duplicates(["county_code", "year"]).sort_values(["county_code", "year"])
        out.to_parquet(OUT, index=False)
        print(f"✅ {OUT} | {len(out)} 行 | {out['county_code'].nunique()} 县 | {out['year'].min()}-{out['year'].max()}")
    else:
        print("⚠️ 无数据产出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
