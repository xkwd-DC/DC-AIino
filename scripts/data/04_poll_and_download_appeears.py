"""轮询 AppEEARS 任务状态 + 下载完成的产物。

输入：`data/interim/appeears_tasks.json`（由 03 脚本写入）
输出：`/mnt/data/DC/modis_ndvi/<year>/` 和 `/mnt/data/DC/modis_lst/<year>/`
      （`data/raw/modis_ndvi` 和 `data/raw/modis_lst` 是它们的 symlink）

策略：
- 默认 `poll`：拉所有 pending/processing 任务的状态，更新 registry，不下载
- `--download` 附加：把 status=done 的任务的 bundle 拉到本地
- 支持反复跑（断点续传 / 跳过已下载）

CLI:
    python scripts/data/04_poll_and_download_appeears.py                          # 只轮询
    python scripts/data/04_poll_and_download_appeears.py --download               # 轮询 + 下载已完成的
    python scripts/data/04_poll_and_download_appeears.py --watch 300              # 每 5 分钟轮询一次直到全部 done
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = PROJECT_ROOT / "data" / "interim" / "appeears_tasks.json"
DEFAULT_ENV = PROJECT_ROOT / ".env"

# 实际产物落到大盘，data/raw/modis_* 是 symlink
MODIS_NDVI_ROOT = PROJECT_ROOT / "data" / "raw" / "modis_ndvi"
MODIS_LST_ROOT = PROJECT_ROOT / "data" / "raw" / "modis_lst"

APPEEARS_BASE = "https://appeears.earthdatacloud.nasa.gov/api"
TIMEOUT = 60
CHUNK = 1024 * 1024


def _load_env(env_path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        pairs[k.strip()] = v.strip()
    return pairs


def appeears_login(username: str, password: str) -> str:
    resp = requests.post(
        f"{APPEEARS_BASE}/login",
        auth=(username, password),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def get_task_status(token: str, task_id: str) -> dict:
    resp = requests.get(
        f"{APPEEARS_BASE}/task/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_bundle(token: str, task_id: str) -> dict:
    """列出任务产物 (files)。"""
    resp = requests.get(
        f"{APPEEARS_BASE}/bundle/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _layer_dest(year: int, layer_name: str) -> Path:
    """根据 layer/产品名分流到 ndvi 或 lst 目录。"""
    upper = layer_name.upper()
    if "NDVI" in upper or "VI_QUALITY" in upper:
        root = MODIS_NDVI_ROOT
    elif "LST" in upper or "QC_DAY" in upper or "QC_NIGHT" in upper:
        root = MODIS_LST_ROOT
    else:
        root = MODIS_NDVI_ROOT  # 兜底，不应该走到
    return root / str(year)


def _download_file(token: str, task_id: str, file_id: str, file_name: str, file_size: int, dest_dir: Path) -> None:
    dest = dest_dir / file_name
    if dest.exists() and dest.stat().st_size == file_size:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    already = partial.stat().st_size if partial.exists() else 0
    headers = {"Authorization": f"Bearer {token}"}
    if already > 0 and already < file_size:
        headers["Range"] = f"bytes={already}-"

    with requests.get(
        f"{APPEEARS_BASE}/bundle/{task_id}/{file_id}",
        headers=headers,
        stream=True,
        timeout=TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        mode = "ab" if already > 0 and resp.status_code == 206 else "wb"
        if mode == "wb":
            already = 0
        with partial.open(mode) as fp, tqdm(
            total=file_size, initial=already, unit="B", unit_scale=True, unit_divisor=1024,
            desc=file_name[:60], leave=False,
        ) as bar:
            for chunk in resp.iter_content(chunk_size=CHUNK):
                if not chunk:
                    continue
                fp.write(chunk)
                bar.update(len(chunk))

    if partial.stat().st_size != file_size:
        raise RuntimeError(f"{file_name} 大小不对 {partial.stat().st_size} vs {file_size}")
    partial.rename(dest)


def poll_once(token: str, registry: dict, *, do_download: bool) -> None:
    summary: Counter[str] = Counter()
    for key, entry in registry.items():
        tid = entry.get("task_id")
        if not tid:
            continue
        try:
            detail = get_task_status(token, tid)
        except requests.HTTPError as e:
            logging.warning("%s 状态拉取失败：%s", key, e)
            continue
        status = detail.get("status", "?")
        entry["status"] = status
        entry["last_polled"] = detail.get("updated")
        summary[status] += 1
        logging.info("year=%s task=%s status=%s", key, tid[:8], status)

        if status == "done" and do_download:
            try:
                bundle = get_bundle(token, tid)
            except requests.HTTPError as e:
                logging.warning("%s bundle 列表失败：%s", key, e)
                continue
            files = bundle.get("files", [])
            year = int(key)
            for f in files:
                fname = f.get("file_name", "?")
                fid = f.get("file_id")
                fsize = f.get("file_size", 0)
                if not fid:
                    continue
                dest_dir = _layer_dest(year, fname)
                try:
                    _download_file(token, tid, fid, fname, fsize, dest_dir)
                except Exception as e:
                    logging.warning("%s 下载 %s 失败：%s", key, fname, e)
            entry["downloaded"] = True
            logging.info("✅ %s 下载完成 (%d 文件)", key, len(files))

    logging.info("汇总：%s", dict(summary))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AppEEARS 任务轮询 + 下载")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--download", action="store_true", help="同时下载已 done 的任务")
    parser.add_argument(
        "--watch",
        type=int,
        metavar="SEC",
        help="间隔 SEC 秒持续轮询直到全部 done（同时启用 --download）",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.registry.exists():
        logging.error("找不到 %s——先跑 03_request_modis_appeears.py", args.registry)
        return 1

    env = _load_env(args.env)
    token = appeears_login(env["EARTHDATA_USERNAME"], env["EARTHDATA_PASSWORD"])

    while True:
        registry = json.loads(args.registry.read_text())
        do_dl = args.download or args.watch is not None
        poll_once(token, registry, do_download=do_dl)
        args.registry.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        statuses = [e.get("status") for e in registry.values() if e.get("task_id")]
        all_done = all(s == "done" for s in statuses) and len(statuses) > 0
        if args.watch is None or all_done:
            if all_done:
                logging.info("🎉 所有任务都 done，结束监听")
            break
        logging.info("睡 %d 秒后再轮询", args.watch)
        time.sleep(args.watch)

    return 0


if __name__ == "__main__":
    sys.exit(main())
