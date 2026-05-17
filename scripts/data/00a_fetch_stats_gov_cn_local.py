"""国家统计局 fsnd（分省年度）数据抓取——**必须在国内 IP 下运行**。

⚠️  Windows + Python 3.12+ 下 stats.gov.cn 的 WAF 会基于 TLS 指纹（JA3）
    识别 Python requests/urllib3 并 403 屏蔽所有 API endpoint。
    本脚本**改用 Windows 自带的 curl.exe 走 subprocess**——curl 用 SChannel，
    TLS 指纹和浏览器一致，能过 WAF。

依赖（极简）：
    pip install pandas         # 仅 pandas，HTTP 走 curl.exe
    # 不需要 requests / curl_cffi / 等等

前提：
    - Windows 10/11 自带 curl.exe（系统 PATH 里）
    - CN 大陆 IP（学校/家庭网，不要走境外代理）

用法：

    # 1. 探索（列出 A0D 农业大类的子指标，肉眼对照 INDICATORS）
    python 00a_fetch_stats_gov_cn_local.py --explore

    # 2. 跑全量抓取
    python 00a_fetch_stats_gov_cn_local.py --years 2011-2023

输出：
    out/yield.csv          粮食单位面积产量
    out/irr_area.csv       有效灌溉面积
    out/mech.csv           农业机械总动力
    out/fert.csv           化肥施用量
    out/disaster.csv       农作物受灾面积
    out/stats_panel.csv    合并后的宽表（你只需要回传这一份）

⚠️  Indicator code 不一定全对！跑 --explore 看实际 code 树，对照 INDICATORS
    第一列改 code。
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

API = "https://data.stats.gov.cn/easyquery.htm"
HOME = "https://data.stats.gov.cn/"
DBCODE = "fsnd"  # 分省年度
TIMEOUT = 30
COOKIES_FILE = "stats_cookies.txt"

INDICATORS = [
    # (内部列名,    候选 zb code 列表,                       预期指标名包含,  单位)
    ("yield",       ["A0D0F", "A0D0K", "A0D0G"],            "粮食",          "公斤/公顷"),
    ("grain_sown",  ["A0D02", "A0D03"],                     "粮食",          "千公顷"),
    ("irr_area",    ["A0D0L", "A0D0K", "A0D0M02"],          "灌溉",          "千公顷"),
    ("mech",        ["A0D0H", "A0D0I"],                     "机械",          "万千瓦"),
    ("fert",        ["A0D0J", "A0D0I"],                     "化肥",          "万吨"),
    ("disaster",    ["A0D0M", "A0D0N"],                     "受灾",          "千公顷"),
]

OUT_DIR = Path("out")

HEADERS = [
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept: application/json, text/javascript, */*; q=0.01",
    "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
    "Referer: https://data.stats.gov.cn/easyquery.htm",
    "X-Requested-With: XMLHttpRequest",
]


def find_curl() -> str:
    """定位 curl.exe（Windows 10+ 自带）。"""
    for cmd in ("curl.exe", "curl"):
        path = shutil.which(cmd)
        if path:
            return path
    # Windows 自带路径
    win_default = Path(r"C:\Windows\System32\curl.exe")
    if win_default.exists():
        return str(win_default)
    raise SystemExit(
        "找不到 curl.exe。Windows 10/11 应自带于 C:\\Windows\\System32\\curl.exe。"
        "Win7/8 请去 https://curl.se/windows/ 下载并加 PATH。"
    )


def curl_get(curl: str, url: str, cookies_file: str, *, follow_redirects: bool = True) -> str:
    """用 curl.exe 发 GET。返回响应 body 字符串。"""
    args = [
        curl, "-sS", "--max-time", str(TIMEOUT),
        "-c", cookies_file, "-b", cookies_file,
    ]
    if follow_redirects:
        args.append("-L")
    for h in HEADERS:
        args.extend(["-H", h])
    args.append(url)
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT + 10)
    if proc.returncode != 0:
        raise RuntimeError(f"curl 退出码 {proc.returncode}：{proc.stderr[:200]}")
    return proc.stdout


def init_session(curl: str, cookies_file: str) -> None:
    """先 GET 主页拿 JSESSIONID。"""
    logging.debug("初始化 cookies → %s", cookies_file)
    curl_get(curl, HOME, cookies_file)


def query(curl: str, cookies_file: str, zb: str, sj: str) -> dict:
    params = {
        "m": "QueryData",
        "dbcode": DBCODE,
        "rowcode": "reg",
        "colcode": "sj",
        "wds": "[]",
        "dfwds": json.dumps([{"wdcode": "zb", "valuecode": zb},
                             {"wdcode": "sj", "valuecode": sj}]),
        "k1": str(int(time.time() * 1000)),
    }
    url = f"{API}?{urlencode(params)}"
    body = curl_get(curl, url, cookies_file)
    if not body.strip():
        raise RuntimeError("响应为空")
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"响应非 JSON（前 200 字符）：{body[:200]!r}") from e


def explore(curl: str, cookies_file: str, parent_id: str = "A0D") -> None:
    params = {
        "m": "getTree",
        "id": parent_id,
        "dbcode": DBCODE,
        "wdcode": "zb",
    }
    url = f"{API}?{urlencode(params)}"
    body = curl_get(curl, url, cookies_file)
    if not body.strip():
        raise RuntimeError("getTree 响应为空")
    try:
        items = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"getTree 响应非 JSON：{body[:300]!r}")
    print(f"\n=== {parent_id} 下子节点 ===")
    print(f"{'code':12s} {'isParent':10s} {'name'}")
    for it in items:
        is_p = "[+]" if it.get("isParent") else "   "
        print(f"  {it['id']:12s} {is_p:10s} {it['name']}")
    print("\n(若 isParent=[+]，加 --explore-id <code> 继续展开)")


def parse_panel(payload: dict, our_col: str) -> tuple[list[dict], str]:
    nodes = payload.get("returndata", {}).get("datanodes", [])
    wdnodes = payload.get("returndata", {}).get("wdnodes", [])
    reg_map = {n["code"]: n["name"] for w in wdnodes if w["wdcode"] == "reg" for n in w["nodes"]}
    zb_nodes = [n for w in wdnodes if w["wdcode"] == "zb" for n in w["nodes"]]
    indicator_name = zb_nodes[0]["name"] if zb_nodes else "?"

    rows = []
    for node in nodes:
        wds = {w["wdcode"]: w["valuecode"] for w in node["wds"]}
        reg_code = wds.get("reg")
        sj_code = wds.get("sj")
        if not reg_code or not sj_code:
            continue
        rows.append({
            "province_code": reg_code,
            "province": reg_map.get(reg_code, "?"),
            "year": int(sj_code),
            our_col: node["data"]["data"] if node["data"]["hasdata"] else None,
        })
    return rows, indicator_name


def try_codes(curl: str, cookies_file: str, codes: Iterable[str], sj: str,
              our_col: str, expect_keyword: str) -> tuple[str, list[dict], str] | None:
    for code in codes:
        try:
            payload = query(curl, cookies_file, code, sj)
        except Exception as e:
            logging.warning("  zb=%s 请求失败：%s", code, str(e)[:120])
            continue
        try:
            rows, name = parse_panel(payload, our_col)
        except Exception as e:
            logging.warning("  zb=%s 解析失败：%s", code, str(e)[:120])
            continue
        if expect_keyword in name:
            return code, rows, name
        logging.info("  zb=%s 得 '%s'，不含 '%s'，继续试下个", code, name, expect_keyword)
        time.sleep(1.0)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="国家统计局 fsnd 数据抓取（仅 CN IP 可用，走 curl.exe）")
    parser.add_argument("--years", type=str, default="2011-2023")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--explore", action="store_true", help="只列 A0D 子节点")
    parser.add_argument("--explore-id", type=str, default="A0D")
    parser.add_argument("--cookies", type=str, default=COOKIES_FILE)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    curl = find_curl()
    logging.info("使用 curl: %s", curl)
    init_session(curl, args.cookies)

    if args.explore:
        explore(curl, args.cookies, args.explore_id)
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    sj = f"{args.years.split('-')[0]}-{args.years.split('-')[1]}"

    all_dfs: dict[str, list[dict]] = {}
    for col, codes, expect, unit in INDICATORS:
        logging.info("=== 抓 %s (候选 %s, 期望含 '%s', 单位 %s) ===", col, codes, expect, unit)
        result = try_codes(curl, args.cookies, codes, sj, col, expect)
        if result is None:
            logging.error("❌ %s 所有候选 code 都没匹配上 → 跑 --explore 看实际 code", col)
            continue
        code, rows, name = result
        logging.info("✅ %s 用 zb=%s 拿到 '%s'，%d 行", col, code, name, len(rows))
        out_csv = args.out / f"{col}.csv"
        with out_csv.open("w", encoding="utf-8", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=["province_code", "province", "year", col])
            w.writeheader()
            w.writerows(rows)
        logging.info("   写入 %s", out_csv)
        all_dfs[col] = rows
        time.sleep(1.5)

    if all_dfs:
        first_col = next(iter(all_dfs))
        keys = {(r["province_code"], r["year"]): {"province_code": r["province_code"],
                                                   "province": r["province"],
                                                   "year": r["year"]}
                for r in all_dfs[first_col]}
        for col, rows in all_dfs.items():
            for r in rows:
                key = (r["province_code"], r["year"])
                if key in keys:
                    keys[key][col] = r[col]
        wide = list(keys.values())
        wide_csv = args.out / "stats_panel.csv"
        fields = ["province_code", "province", "year"] + list(all_dfs.keys())
        with wide_csv.open("w", encoding="utf-8", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=fields)
            w.writeheader()
            w.writerows(wide)
        logging.info("✅ 合并宽表 %s（%d 行 × %d 列）", wide_csv, len(wide), len(fields))
        logging.info("把 %s 传回服务器 data/raw/paper_panel/", wide_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
