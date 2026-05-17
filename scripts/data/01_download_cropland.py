"""下载 CLCD（China Land Cover Dataset）2011-2023 逐年 30m 耕地数据。

来源：Yang & Huang (2021), ESSD 13:3907–3925，Zenodo record 12779975
许可：CC-BY-4.0
契约：docs/08_数据采集任务_石灵子.md §5.1

输出：`data/raw/gis_cropland/CLCD_v01_YYYY_albert.tif`（Albers Equal Area 投影，约 800 MB/年）

不需要账号。Zenodo 直链下载，支持断点续传。

CLI:
    python scripts/data/01_download_cropland.py                    # 默认 2011-2023
    python scripts/data/01_download_cropland.py --year 2022        # 单年（先小样本验证）
    python scripts/data/01_download_cropland.py --years 2015-2020  # 范围
    python scripts/data/01_download_cropland.py --dry-run          # 只打印不下载
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "raw" / "gis_cropland"

ZENODO_RECORD_ID = "12779975"
ZENODO_API = f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}"
FILENAME_TEMPLATE = "CLCD_v01_{year}_albert.tif"

DEFAULT_YEAR_RANGE = (2011, 2023)
CHUNK_SIZE = 1024 * 1024  # 1 MiB
REQUEST_TIMEOUT = 60  # seconds


@dataclass(frozen=True)
class ZenodoFile:
    name: str
    size: int
    url: str


def _fetch_record_files() -> dict[str, ZenodoFile]:
    """从 Zenodo API 读取本 record 所有文件的 (name, size, url) 映射。"""
    logging.info("查询 Zenodo record %s ...", ZENODO_RECORD_ID)
    resp = requests.get(ZENODO_API, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    record = resp.json()
    files: dict[str, ZenodoFile] = {}
    for entry in record.get("files", []):
        key = entry["key"]
        files[key] = ZenodoFile(
            name=key,
            size=entry["size"],
            url=entry["links"]["self"],
        )
    logging.info("Zenodo record 共 %d 个文件", len(files))
    return files


def _parse_years(year: int | None, years: str | None) -> list[int]:
    if year is not None and years is not None:
        raise SystemExit("不要同时传 --year 和 --years")
    if year is not None:
        return [year]
    if years is not None:
        if "-" not in years:
            raise SystemExit(f"--years 格式应为 'START-END'，例如 2011-2023；收到 {years!r}")
        lo, hi = years.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return list(range(DEFAULT_YEAR_RANGE[0], DEFAULT_YEAR_RANGE[1] + 1))


def _download_with_resume(zfile: ZenodoFile, dest: Path) -> None:
    """流式下载，支持断点续传。完成后大小必须等于 Zenodo 报告的 size。"""
    partial = dest.with_suffix(dest.suffix + ".partial")
    already = partial.stat().st_size if partial.exists() else 0

    if already > zfile.size:
        logging.warning("%s 残留文件 %d B > 期望 %d B，删除重下", partial.name, already, zfile.size)
        partial.unlink()
        already = 0

    if already == zfile.size:
        partial.rename(dest)
        logging.info("%s 已完整，重命名为最终文件", dest.name)
        return

    headers = {"Range": f"bytes={already}-"} if already > 0 else {}
    mode = "ab" if already > 0 else "wb"
    if already > 0:
        logging.info("断点续传 %s 从 %d B（共 %d B）", dest.name, already, zfile.size)

    with requests.get(zfile.url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        with partial.open(mode) as fp, tqdm(
            total=zfile.size,
            initial=already,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=dest.name,
        ) as bar:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                fp.write(chunk)
                bar.update(len(chunk))

    final_size = partial.stat().st_size
    if final_size != zfile.size:
        raise RuntimeError(
            f"{dest.name} 下载完成后大小 {final_size} B ≠ 期望 {zfile.size} B，已保留 .partial"
        )
    partial.rename(dest)


def download_years(years: list[int], out_dir: Path, *, dry_run: bool = False) -> int:
    """返回成功下载（或已存在）的年份数。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    available = _fetch_record_files()

    successes = 0
    for year in years:
        filename = FILENAME_TEMPLATE.format(year=year)
        if filename not in available:
            logging.error("Zenodo record 不含 %s（可下载年份：%s）", filename, sorted(available.keys())[:5])
            continue

        zfile = available[filename]
        dest = out_dir / filename

        if dest.exists():
            actual = dest.stat().st_size
            if actual == zfile.size:
                logging.info("✅ %s 已存在 (%d B)，跳过", filename, actual)
                successes += 1
                continue
            logging.warning("%s 已存在但大小 %d B ≠ 期望 %d B，将重下", filename, actual, zfile.size)
            dest.unlink()

        if dry_run:
            logging.info("DRY-RUN 将下载 %s (%d B) → %s", filename, zfile.size, dest)
            successes += 1
            continue

        _download_with_resume(zfile, dest)
        successes += 1

    return successes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CLCD 30m 耕地数据下载（Zenodo 12779975，无需账号）",
    )
    parser.add_argument("--year", type=int, help="单年（例如 2022），先小样本验证")
    parser.add_argument("--years", type=str, help="年份范围 'START-END'，例如 2011-2023")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印不下载")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    years = _parse_years(args.year, args.years)
    logging.info("目标年份：%s → %s", years, args.out_dir)

    succeeded = download_years(years, args.out_dir, dry_run=args.dry_run)
    logging.info("完成 %d / %d 年", succeeded, len(years))
    return 0 if succeeded == len(years) else 1


if __name__ == "__main__":
    sys.exit(main())
