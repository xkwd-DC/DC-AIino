"""下载省级行政区划 GeoJSON——双源策略。

来源：
  A) DataV.GeoAtlas（阿里）— **GCJ-02 坐标偏移**，仅用于前端 UI 原型/快速调试
     直链：https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json
     无需账号，~3 MB
  B) 天地图 GS(2024)0650 — **WGS84/CGCS2000**，论文/答辩出图与栅格统计必用
     ❗ 需要本人注册天地图账号，网页手动下载 → 放 `data/raw/gis_province/tianditu/`

契约：docs/08_数据采集任务_石灵子.md §5.1

❗ 红线（写脚本时再说一次，免得忘）：
   - DataV 与 MODIS 叠加偏移 50–500m，**绝对不要用 DataV 做 zonal_stats**
   - GADM / Natural Earth 边界违规，不要下

CLI:
    python scripts/data/02_download_province_geojson.py
    python scripts/data/02_download_province_geojson.py --include-provinces  # 同时下 31 个省级单独 GeoJSON
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "raw" / "gis_province"

DATAV_BASE = "https://geo.datav.aliyun.com/areas_v3/bound"
DATAV_COUNTRY = f"{DATAV_BASE}/100000_full.json"
REQUEST_TIMEOUT = 30

# 民政部 6 位省级行政区划代码（DataV 用前两位 + "0000"）
PROVINCE_CODES: tuple[tuple[str, str], ...] = (
    ("110000", "北京市"),
    ("120000", "天津市"),
    ("130000", "河北省"),
    ("140000", "山西省"),
    ("150000", "内蒙古自治区"),
    ("210000", "辽宁省"),
    ("220000", "吉林省"),
    ("230000", "黑龙江省"),
    ("310000", "上海市"),
    ("320000", "江苏省"),
    ("330000", "浙江省"),
    ("340000", "安徽省"),
    ("350000", "福建省"),
    ("360000", "江西省"),
    ("370000", "山东省"),
    ("410000", "河南省"),
    ("420000", "湖北省"),
    ("430000", "湖南省"),
    ("440000", "广东省"),
    ("450000", "广西壮族自治区"),
    ("460000", "海南省"),
    ("500000", "重庆市"),
    ("510000", "四川省"),
    ("520000", "贵州省"),
    ("530000", "云南省"),
    ("540000", "西藏自治区"),
    ("610000", "陕西省"),
    ("620000", "甘肃省"),
    ("630000", "青海省"),
    ("640000", "宁夏回族自治区"),
    ("650000", "新疆维吾尔自治区"),
)


def _download_json(url: str, dest: Path) -> int:
    """下载一个 JSON 文件，返回字节数。已存在则跳过。"""
    if dest.exists() and dest.stat().st_size > 0:
        logging.debug("跳过已存在 %s (%d B)", dest.name, dest.stat().st_size)
        return dest.stat().st_size
    logging.info("GET %s", url)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return len(resp.content)


def download_datav(out_dir: Path, *, include_provinces: bool) -> None:
    datav_dir = out_dir / "datav"
    datav_dir.mkdir(parents=True, exist_ok=True)

    total = _download_json(DATAV_COUNTRY, datav_dir / "100000_full.json")
    logging.info("✅ DataV 全国 GeoJSON: %d B", total)

    if not include_provinces:
        return

    logging.info("拉 31 个省级 GeoJSON ...")
    bar = tqdm(PROVINCE_CODES, desc="DataV 省级", unit="省")
    for code, name in bar:
        bar.set_postfix_str(name)
        url = f"{DATAV_BASE}/{code}_full.json"
        dest = datav_dir / f"{code}_full.json"
        try:
            _download_json(url, dest)
        except requests.HTTPError as exc:  # 个别省可能没有 _full 端点
            logging.warning("跳过 %s (%s)：%s", code, name, exc)


def write_tianditu_manual_readme(out_dir: Path) -> None:
    """天地图必须本人登录下载，写一份操作指引到 raw/gis_province/tianditu/README.md。"""
    tdt_dir = out_dir / "tianditu"
    tdt_dir.mkdir(parents=True, exist_ok=True)
    readme = tdt_dir / "README.md"
    if readme.exists():
        return
    readme.write_text(
        """# 天地图行政区划（GS(2024)0650）— 手动下载步骤

> 你（石灵子）本人操作，因为天地图要求实名注册账号。

## 步骤

1. 注册天地图账号：https://map.tianditu.gov.cn/
   - 邮箱 + 手机号双验证
2. 进行政区划下载中心：https://cloudcenter.tianditu.gov.cn/administrativeDivision
3. 选 **2024 三级行政区划数据库**（带审图号 GS(2024)0650）
4. 下载 **省级**（如果有省+市+县的合包就下合包）
5. 解压到本目录（`data/raw/gis_province/tianditu/`），保留原文件名
6. 在群里同步一句"天地图省界下完了，N MB"

## 为什么必须用天地图

- 论文 / 答辩 PPT 公开图件**必须**带审图号底图（自然资源部要求）
- DataV.GeoAtlas 那一份 GCJ-02 坐标偏移，且无审图号，**不能用于发表的成图**
- GADM / Natural Earth 边界争议（藏南、台湾），**直接拒收**

## 关键参数对比（验收时核对）

| 项 | 应当值 |
|---|---|
| 坐标系 | CGCS2000 或 WGS84（不是 GCJ-02 / BD-09） |
| 审图号 | GS(2024)0650 |
| 九段线 | ✅ 包含 |
| 省份数 | 34（含港澳台） |

下完之后跑 `python scripts/data/02_download_province_geojson.py --verify-tianditu` 做一次完整性自检（待实现）。
""",
        encoding="utf-8",
    )
    logging.info("天地图手动下载指引：%s", readme)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="省级行政区划 GeoJSON 下载（DataV 自动 + 天地图手动指引）",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出根目录"
    )
    parser.add_argument(
        "--include-provinces",
        action="store_true",
        help="同时下载 31 个省级单独 GeoJSON（DataV 端，约 30 MB）",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    download_datav(args.out_dir, include_provinces=args.include_provinces)
    write_tianditu_manual_readme(args.out_dir)

    logging.warning(
        "⚠️ DataV 是 GCJ-02 偏移坐标，仅作前端 UI 原型；栅格统计/论文出图务必等天地图下完"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
