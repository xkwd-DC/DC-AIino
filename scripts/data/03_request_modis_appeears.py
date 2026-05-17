"""向 NASA AppEEARS 提交 MODIS 区域子集任务（中国 + 2011-2023 + NDVI/LST）。

依赖：
  - `.env` 含 EARTHDATA_USERNAME / EARTHDATA_PASSWORD
  - `data/interim/china_roi_for_appeears.geojson` 已由 `_build_china_roi.py` 生成

策略：**每年一个任务**——AppEEARS 单任务体积有限，13 年并行提交，后台同时处理。
任务 ID 写到 `data/interim/appeears_tasks.json`，给 04 脚本轮询/下载用。

CLI:
    python scripts/data/03_request_modis_appeears.py --year 2022                    # 单年测试
    python scripts/data/03_request_modis_appeears.py --years 2011-2023 --submit     # 真提交
    python scripts/data/03_request_modis_appeears.py --years 2011-2023              # dry-run（默认）
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROI = PROJECT_ROOT / "data" / "interim" / "china_roi_for_appeears.geojson"
DEFAULT_TASKS_REGISTRY = PROJECT_ROOT / "data" / "interim" / "appeears_tasks.json"
DEFAULT_ENV = PROJECT_ROOT / ".env"

APPEEARS_BASE = "https://appeears.earthdatacloud.nasa.gov/api"
TIMEOUT = 60

# 拉的产品 + 波段。
# - MOD13A3：月度 1km NDVI——项目 11 维特征的 NDVI 列直接用这个
# - MOD11A2：8 天 1km LST 白天/夜间——本地合成月度
# - QC 波段一定要带，下游聚合时按 reliability 过滤云污染像元
#
# 2026-05-16 精简：去掉 EVI（项目不需要，省 1/3 出包体积）
LAYERS = [
    {"product": "MOD13A3.061", "layer": "_1_km_monthly_NDVI"},
    {"product": "MOD13A3.061", "layer": "_1_km_monthly_VI_Quality"},
    {"product": "MOD11A2.061", "layer": "LST_Day_1km"},
    {"product": "MOD11A2.061", "layer": "LST_Night_1km"},
    {"product": "MOD11A2.061", "layer": "QC_Day"},
    {"product": "MOD11A2.061", "layer": "QC_Night"},
]


def _load_env(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        raise SystemExit(f"找不到 {env_path}——先把 NASA 凭证写进 .env")
    pairs: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        pairs[k.strip()] = v.strip()
    return pairs


def appeears_login(username: str, password: str) -> str:
    logging.info("AppEEARS 登录中（用户 %s）...", username)
    resp = requests.post(
        f"{APPEEARS_BASE}/login",
        auth=(username, password),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"AppEEARS 登录失败 [{resp.status_code}]：{resp.text[:200]}")
    payload = resp.json()
    logging.info("token 有效期至 %s", payload.get("expiration"))
    return payload["token"]


def build_task(year: int, roi_feature: dict) -> dict:
    return {
        "task_type": "area",
        "task_name": f"DC-MODIS-China-{year}",
        "params": {
            "dates": [
                {
                    "startDate": f"01-01-{year}",
                    "endDate": f"12-31-{year}",
                }
            ],
            "layers": LAYERS,
            "geo": {
                "type": "FeatureCollection",
                "features": [roi_feature],
                "fileName": f"china_roi_{year}",
            },
            "output": {
                "format": {"type": "geotiff"},
                "projection": "geographic",  # WGS84 经纬度，下游 zonal_stats 配 EPSG:4326
            },
        },
    }


def submit_task(token: str, task: dict) -> dict:
    resp = requests.post(
        f"{APPEEARS_BASE}/task",
        json=task,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"AppEEARS 提交失败 [{resp.status_code}]：{resp.text[:500]}")
    return resp.json()


def parse_years(year: int | None, years: str | None) -> list[int]:
    if year is not None and years is not None:
        raise SystemExit("不要同时传 --year 和 --years")
    if year is not None:
        return [year]
    if years is not None:
        if "-" not in years:
            raise SystemExit(f"--years 格式 'START-END'，收到 {years!r}")
        lo, hi = years.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return list(range(2011, 2024))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提交 AppEEARS MODIS 中国区域任务")
    parser.add_argument("--year", type=int)
    parser.add_argument("--years", type=str, help="年份范围 START-END，例 2011-2023")
    parser.add_argument("--roi", type=Path, default=DEFAULT_ROI)
    parser.add_argument("--registry", type=Path, default=DEFAULT_TASKS_REGISTRY)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--submit", action="store_true", help="真提交（默认 dry-run）")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.roi.exists():
        logging.error("找不到 ROI 文件 %s——先跑 _build_china_roi.py", args.roi)
        return 1

    roi_fc = json.loads(args.roi.read_text())
    roi_feature = roi_fc["features"][0]
    years = parse_years(args.year, args.years)
    logging.info("目标年份：%s", years)

    env = _load_env(args.env)
    os.environ.update(env)

    if args.submit:
        token = appeears_login(env["EARTHDATA_USERNAME"], env["EARTHDATA_PASSWORD"])
    else:
        token = "DRY-RUN-TOKEN"
        logging.warning("DRY-RUN：不会真提交。加 --submit 实际跑")

    # 读现有 registry（断点续传 / 重提）
    registry: dict[str, dict] = {}
    if args.registry.exists():
        registry = json.loads(args.registry.read_text())
        logging.info("registry 现有 %d 个任务记录", len(registry))

    for year in years:
        key = str(year)
        if key in registry and registry[key].get("task_id"):
            logging.info("%s 已有任务 %s，跳过", year, registry[key]["task_id"])
            continue

        task = build_task(year, roi_feature)
        if args.verbose:
            logging.debug("task[%s] = %s", year, json.dumps(task, ensure_ascii=False)[:500])

        if args.submit:
            try:
                result = submit_task(token, task)
            except RuntimeError as e:
                logging.error("%s 提交失败：%s", year, e)
                continue
            tid = result.get("task_id")
            logging.info("✅ %s task_id=%s status=%s", year, tid, result.get("status"))
            registry[key] = {
                "task_id": tid,
                "task_name": task["task_name"],
                "year": year,
                "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": result.get("status", "submitted"),
                "layers": [f"{l['product']}/{l['layer']}" for l in LAYERS],
            }
        else:
            logging.info("[DRY-RUN] 将提交 %s，layers=%d 个，ROI bounds 约 73-135°E / 4-54°N",
                        task["task_name"], len(LAYERS))
            registry[key] = {
                "task_id": None,
                "task_name": task["task_name"],
                "year": year,
                "dry_run": True,
            }

    args.registry.parent.mkdir(parents=True, exist_ok=True)
    args.registry.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("registry 写入 %s", args.registry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
