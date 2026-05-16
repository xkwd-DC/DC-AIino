"""国家统计局 fsnd（分省年度）数据抓取——**必须在国内 IP 下运行**。

从这台机的 GCP IP 访问 stats.gov.cn 被 WAF UrlACL 直接拒。
石灵子在自己的电脑/校园网（CN 大陆 IP）跑这个脚本，然后把输出 CSV 传回服务器。

依赖（极简）：
    pip install requests pandas

用法：

    # 1. 先探索模式：列出 A0D（农业）大类下的所有指标，肉眼对照本脚本里的候选 code
    python 00a_fetch_stats_gov_cn_local.py --explore

    # 2. 跑全量抓取（5 个指标 × 31 省 × 13 年，~30 秒）
    python 00a_fetch_stats_gov_cn_local.py --years 2011-2023

输出：
    out/yield.csv          粮食单位面积产量
    out/irr_area.csv       有效灌溉面积
    out/mech.csv           农业机械总动力
    out/fert.csv           化肥施用量
    out/disaster.csv       农作物受灾面积
    out/stats_panel.csv    合并后的宽表（你只需要回传这一份）

⚠️  Indicator code 不一定全对！每个 fetch 完会打印「拿到的指标名」，对比预期：
    - 名字对得上 → 数据可用
    - 名字对不上 → 改 `INDICATORS` 里的 `code` 重试
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import ssl
import sys
import time
from pathlib import Path
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

API = "https://data.stats.gov.cn/easyquery.htm"
DBCODE = "fsnd"  # 分省年度
TIMEOUT = 30


class LegacyTLSAdapter(HTTPAdapter):
    """国家统计局服务器的 TLS 实现老旧，Python 3.12+ 默认 security level=2 会握手失败。

    把 SECLEVEL 降到 1 + 启用 unsafe_legacy_renegotiation 才能连上。
    """

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        # OpenSSL 3.0+ 默认禁掉了 legacy renegotiation；statics 服务器需要
        try:
            ctx.options |= 0x4  # ssl.OP_LEGACY_SERVER_CONNECT
        except AttributeError:
            pass
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        try:
            ctx.options |= 0x4
        except AttributeError:
            pass
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().proxy_manager_for(*args, **kwargs)

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


def make_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", LegacyTLSAdapter())
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://data.stats.gov.cn/easyquery.htm",
        "X-Requested-With": "XMLHttpRequest",
    })
    # InsecureRequestWarning 静音
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass
    # 拿 JSESSIONID；连不通就让上层处理
    s.get("https://data.stats.gov.cn/", timeout=TIMEOUT, verify=False)
    return s


def query(session: requests.Session, zb: str, sj: str) -> dict:
    """一次拉 31 省 × N 年。"""
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
    r = session.get(API, params=params, timeout=TIMEOUT, verify=False)
    r.raise_for_status()
    return r.json()


def explore(session: requests.Session, parent_id: str = "A0D") -> None:
    """打印 parent_id 下所有子指标，肉眼匹配 code。"""
    r = session.get(
        API,
        params={
            "m": "getTree",
            "id": parent_id,
            "dbcode": DBCODE,
            "wdcode": "zb",
        },
        timeout=TIMEOUT,
        verify=False,
    )
    r.raise_for_status()
    items = r.json()
    print(f"\n=== {parent_id} 下子节点 ===")
    print(f"{'code':12s} {'isParent':10s} {'name'}")
    for it in items:
        is_p = "[+]" if it.get("isParent") else "   "
        print(f"  {it['id']:12s} {is_p:10s} {it['name']}")
    print("\n(树形）若 isParent=true，可加 --explore-id <code> 继续展开")


def parse_panel(payload: dict, our_col: str) -> tuple[list[dict], str]:
    """提取 returndata.datanodes → 31 省 × N 年。返回 (rows, indicator_name)。"""
    nodes = payload.get("returndata", {}).get("datanodes", [])
    wdnodes = payload.get("returndata", {}).get("wdnodes", [])

    sj_map = {n["code"]: n["name"] for w in wdnodes if w["wdcode"] == "sj" for n in w["nodes"]}
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


def try_codes(session: requests.Session, codes: Iterable[str], sj: str, our_col: str,
              expect_keyword: str) -> tuple[str, list[dict], str] | None:
    """依次试候选 code，第一个名字包含期望关键词的就用。"""
    for code in codes:
        try:
            payload = query(session, code, sj)
        except Exception as e:
            logging.warning("  zb=%s 请求失败：%s", code, e)
            continue
        try:
            rows, name = parse_panel(payload, our_col)
        except Exception as e:
            logging.warning("  zb=%s 解析失败：%s", code, e)
            continue
        if expect_keyword in name:
            return code, rows, name
        logging.info("  zb=%s 得 '%s'，不含 '%s'，继续试下个", code, name, expect_keyword)
        time.sleep(1.0)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="国家统计局 fsnd 数据抓取（仅 CN IP 可用）")
    parser.add_argument("--years", type=str, default="2011-2023")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--explore", action="store_true", help="只打印 A0D 农业大类的指标列表")
    parser.add_argument("--explore-id", type=str, default="A0D", help="自定义探索节点 id")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    session = make_session()

    if args.explore:
        explore(session, args.explore_id)
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    sj = f"{args.years.split('-')[0]}-{args.years.split('-')[1]}"

    all_dfs: dict[str, list[dict]] = {}
    for col, codes, expect, unit in INDICATORS:
        logging.info("=== 抓 %s (候选 %s, 期望含 '%s', 单位 %s) ===", col, codes, expect, unit)
        result = try_codes(session, codes, sj, col, expect)
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

    # 合并宽表
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
        logging.info("把 %s 传回 /home/darcy/DC/DC/data/raw/paper_panel/", wide_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
