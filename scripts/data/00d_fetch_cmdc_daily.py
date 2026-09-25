"""中国气象数据网 (CMDC) 气候数据存储 API —— 拉取气象站日值/逐时数据。

官方 SDK：https://data.cma.cn 登录后，在「气候数据存储应用程序接口」页下载
  CMDCapi.zip，解压出 CMDCapi.py 放到本脚本同目录（scripts/data/）即可 import。

前置：.env 里配置账号（详见 .env.example 的 CMDC_USER_ID / CMA_USERNAME）。

⚠️ 每个数据集的 params 不一样（productId / source / elementLayer / cutParam 取决于
你申请的具体产品）。文档示例是再分析产品，不是地面站日值。正确的做法是：
  1) 登录 data.cma.cn，进到你申请通过的那个数据集详情页；
  2) 点它的「显示 API 示例」，把生成的 params 复制出来填到下方 PRODUCTS["daily_v3"] 里。

输出：data/raw/cmdc_daily/<dataset_key>/<yyyy>.zip（或 .txt/.nc，由产品决定）

CLI:
    python scripts/data/00d_fetch_cmdc_daily.py --dry-run            # 只打印请求，不下载
    python scripts/data/00d_fetch_cmdc_daily.py --year 2023          # 单年（试点用）
    python scripts/data/00d_fetch_cmdc_daily.py --pilot              # 最后一年单年，最小量试点
    python scripts/data/00d_fetch_cmdc_daily.py                      # 全量 2012-2024
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "cmdc_daily"
CMDCAPI_MODULE = "CMDCapi"
YEAR_RANGE = range(2012, 2025)  # 2012-2024，窗口与项目对齐

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cmdc")


# ── 数据集参数 ─────────────────────────────────────────────────────────────
# TODO(石灵子): 在你申请到的数据集详情页点「显示 API 示例」，把生成的 params 粘进来。
# 下面只是占位，绝不代表最终值；填好后再跑 --dry-run 校验。
PRODUCTS = {
    "daily_v3": {
        "label": "中国国家级地面气象站基本气象要素日值数据集(V3.0)",
        # ↓↓↓ 以下字段需从「显示 API 示例」替换为实际值 ↓↓↓
        "productId": "TODO",            # 该数据集的 productId
        "source": "TODO",               # 地面站数据源标识
        "area": "中国",                 # 区域
        "cutParam": "TODO",             # 经纬度裁剪范围，如 "-10:30 35:60"
        "elementLayer": "TODO",         # 地面要素字段，如 "TEM_Max:TEM_Max:地面#..."（待核对）
        "aging": "0:0,3,6#12:3,6,9",    # 示例默认，日值产品可能不需要，视 API 示例
        "day": "0",                     # 日值产品通常全月，占位
        "month": "0",                   # 全 12 月
        "hour": "0",                    # 日值无小时维度
        "isSdk": "1",
        "isZip": "1",
    },
}


def _load_credentials() -> tuple[str, str | None]:
    """读 .env 里的 CMDC 账号（API 市场 user_id + 口令），回退到门户账号。

    注意：CMDC_USER_ID 是「气候数据存储 API」市场的用户 ID（形如 7884...），
    不是门户登录邮箱；两者要区分开。
    """
    user_id = os.getenv("CMDC_USER_ID") or os.getenv("CMA_USERNAME")
    password = os.getenv("CMDC_PASSWORD") or os.getenv("CMA_PASSWORD")
    if not user_id:
        raise SystemExit(
            "缺少账号：请在 D:\\DC\\DC-AIino\\.env 里配置 CMDC_USER_ID 或 CMA_USERNAME"
        )
    return user_id, password


def _client(user_id: str, password: str | None, output_dir: Path):
    """导入 CMDCapi 并返回客户端；缺文件时给出明确的提示。"""
    try:
        from CMDCapi import CMDCClient
    except ImportError:
        raise SystemExit(
            "没找到 CMDCapi.py。请到 data.cma.cn 的「气候数据存储应用程序接口」页下载 "
            "CMDCapi.zip，把解压出的 CMDCapi.py 放到 scripts/data/ 下（与本脚本同级）。"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"user_id": user_id, "output_dir": str(output_dir)}
    if password:
        kwargs["password"] = password
    try:
        return CMDCClient(**kwargs)
    except TypeError:
        # 某些版本的 SDK 不暴露 password 参数，去掉后再试
        kwargs.pop("password", None)
        return CMDCClient(**kwargs)


def build_params(product: dict, year: int) -> dict:
    """按数据集模板 + 年份拼出递交给 retrieve 的 params。"""
    params = dict(product)
    params["year"] = str(year)
    # 把占位没填的字段暴露出来，避免带 TODO 直接跑
    if "TODO" in [str(params.get(k)) for k in ("productId", "source", "cutParam", "elementLayer")]:
        missing = [k for k in ("productId", "source", "cutParam", "elementLayer") if str(params.get(k)) == "TODO"]
        raise SystemExit(
            f"params 还没填全，缺：{', '.join(missing)}。请到数据集详情页点「显示 API 示例」后"
            "把实际值填进 scripts/data/00d_fetch_cmdc_daily.py 的 PRODUCTS 里。"
        )
    # 数据存储接口一般要显式带上 sdk/zip 标记
    params["isSdk"] = params.get("isSdk", "1")
    params["isZip"] = params.get("isZip", "1")
    return params


def download_years(product_key: str, years, dry_run: bool) -> None:
    product = PRODUCTS[product_key]
    out_dir = DEFAULT_OUTPUT / product_key
    user_id, password = _load_credentials()
    client = _client(user_id, password, out_dir)

    for year in tqdm(list(years), desc=product_key, unit="year"):
        params = build_params(product, year)
        if dry_run:
            log.info("[dry-run] year=%s params=%s", year, params)
            continue
        # retrieve 失败时给出可读错误，避免静默吞掉整条链路
        try:
            client.retrieve(params)
        except Exception as e:  # noqa: BLE001 —— CMDC SDK 异常类型未知，统一兜底
            log.error("year=%s 下载失败: %s", year, e)
            raise
        log.info("year=%s 完成 → %s", year, out_dir)


def main(argv=None) -> int:
    # Windows GBK 控制台印不出 ⚠️/箭头等字符，强制 UTF-8 输出避免 UnicodeEncodeError
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 —— 仅兜底，不影响主流程
            pass
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="CMDC 气候数据存储 API 取数（详见文件头 docstring 与 PRODUCTS 配置）"
    )
    parser.add_argument("--product", default="daily_v3", choices=list(PRODUCTS), help="数据集 key")
    parser.add_argument(
        "--year",
        nargs="*",
        default=None,
        help="要下载的年份（空格分隔，如 --year 2023 2024）；默认全量",
    )
    parser.add_argument("--pilot", action="store_true", help="只下最后一年，最小量试点")
    parser.add_argument("--dry-run", action="store_true", help="只打印请求，不实际下载")
    parser.add_argument("--output-dir", default=None, help="覆盖默认输出目录（默认 D 盘 data/raw/cmdc_daily/）")
    args = parser.parse_args(argv)

    if args.pilot:
        years = [YEAR_RANGE.stop - 1]  # 2024
    elif args.year:
        years = [int(y) for y in args.year]
    else:
        years = list(YEAR_RANGE)

    download_years(args.product, years, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
