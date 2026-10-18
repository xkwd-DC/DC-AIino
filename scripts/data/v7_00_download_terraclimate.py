#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并行下载 v6/v7 链路所需的 TerraClimate 年度栅格（断点续传 + 完整性校验）。

为什么要单独一个脚本
====================
``v6_01b_terraclimate_county.py`` 里的 ``download()`` 用 4 线程跑，但本机 curl
默认不走系统代理（WinHTTP 是直连，实际代理在 127.0.0.1:7890），所以要么先
设好 ``HTTP_PROXY/HTTPS_PROXY`` 再调用它。本脚本把下载单独抽出来，做成
「8 线程 + 进度日志 + 已完成文件跳过」，便于中断后随时续跑。

总量参考：5 变量 × 2012–2023 = 60 个文件，单文件约 93 MB，合计约 5.6 GB。

用法
====
    $env:HTTP_PROXY='http://127.0.0.1:7890'; $env:HTTPS_PROXY=$env:HTTP_PROXY
    python scripts/data/v7_00_download_terraclimate.py
    python scripts/data/v7_00_download_terraclimate.py --workers 8
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import sys
import time
from pathlib import Path

import netCDF4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.data import v6_01b_terraclimate_county as tc  # noqa: E402


def is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with netCDF4.Dataset(path):
            return True
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    tc.NC_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for var in tc.VARS:
        for year in tc.YEARS:
            fp = tc.NC_DIR / f"TerraClimate_{var}_{year}.nc"
            if not is_complete(fp):
                jobs.append((tc.BASE.format(var=var, year=year), fp))

    total = len(tc.VARS) * len(list(tc.YEARS))
    print(f"{tc.NC_DIR}")
    print(f"已有完整文件 {total - len(jobs)}/{total}，待下载 {len(jobs)} 个，{args.workers} 线程", flush=True)
    if not jobs:
        print("DOWNLOAD DONE")
        return

    started = time.time()
    done = 0
    failed: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(tc._curl_one, url, fp): fp for url, fp in jobs}
        for fut in cf.as_completed(futs):
            fp = futs[fut]
            ok = fut.result()
            done += 1
            size_mb = fp.stat().st_size / 1e6 if fp.exists() else 0.0
            if not ok:
                failed.append(fp.name)
            print(
                f"[{done}/{len(jobs)}] {fp.name} {'OK' if ok else 'FAIL'} "
                f"{size_mb:.0f} MB elapsed {time.time() - started:.0f}s",
                flush=True,
            )
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    print("DOWNLOAD DONE")


if __name__ == "__main__":
    main()
