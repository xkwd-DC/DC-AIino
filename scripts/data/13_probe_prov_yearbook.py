#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""13_probe_prov_yearbook.py — A2 探路：定位各省统计年鉴「县市篇」县级表

背景
====
A1 已否证「从《中国县域统计年鉴》补 2023 县级粮食产量」这条路（该年鉴
2018 卷起整册不再收录粮食总产量/播种面积）。A2 因此成为 P0，且现在同时
承担两件事：
  1. 县级「主要农作物/粮食播种面积」分县表 —— 单产口径的分母
  2. 2023 县级粮食总产量 —— 抹掉「时间只到 2022」的硬伤

山西路径已验证可行（``scripts/sx_data/fetch_sx_sown.py``，2005–2023 每年
一个直链 xls），本脚本把同一套「索引页 → 分卷目录 → 分县表」的定位过程
自动化，用来给其余 9 省定价：哪省结构规整、哪省需要另想办法。

本脚本**只探测、不落数据**，输出候选表清单（URL + 标题 + 类型）。

用法
====
    python scripts/data/13_probe_prov_yearbook.py --province henan
    python scripts/data/13_probe_prov_yearbook.py --province hebei --depth 3
    python scripts/data/13_probe_prov_yearbook.py --list
"""
from __future__ import annotations

import argparse
import re
import ssl
import sys
import urllib.request
from urllib.parse import urljoin

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 省统计局「统计年鉴」索引页。山西单列在 sx_data 下，此处收其余 9 省。
# 入口地址均经 2026-10-15 实测，三处与常见写法不同，别再按「tjj.省.gov.cn」猜：
#   山东：拒 HTTPS（403），只有 http 通；且 IPv4 可用、IPv6 超时
#   江苏：统计局的域名是 tj.jiangsu.gov.cn，tjj.jiangsu.gov.cn 不存在
#   湖南：HTTPS 能用，但 Python 的 OpenSSL 报 BAD_ECPOINT，需走 curl 回退
PROVINCES: dict[str, tuple[str, str]] = {
    "hebei": ("河北", "https://tjj.hebei.gov.cn/"),
    "henan": ("河南", "https://tjj.henan.gov.cn/tjfw/tjcbw/tjnj/"),
    "shandong": ("山东", "http://tjj.shandong.gov.cn/"),
    "jiangsu": ("江苏", "https://tj.jiangsu.gov.cn/"),
    "anhui": ("安徽", "https://tjj.ah.gov.cn/"),
    "hubei": ("湖北", "https://tjj.hubei.gov.cn/"),
    "hunan": ("湖南", "https://tjj.hunan.gov.cn/"),
    "heilongjiang": ("黑龙江", "https://tjj.hlj.gov.cn/"),
    "jilin": ("吉林", "https://tjj.jl.gov.cn/"),
    "sichuan": ("四川", "https://tjj.sc.gov.cn/"),
}

# 县级表标题的特征词。命中的链接才是 A2 的目标。
COUNTY_HINTS = ("分县", "县市", "县（市", "县(市", "县域", "各县", "县区")
TOPIC_HINTS = ("播种面积", "粮食播种", "农作物播种", "粮食产量", "农产品产量", "主要农作物")


def fetch(url: str, timeout: int = 25) -> tuple[int, bytes, str]:
    """取页面。urllib 失败时回退 curl。

    回退不是保险起见：湖南统计局站点的 TLS 会让 Python 的 OpenSSL 抛
    ``BAD_ECPOINT``，而 curl（走系统 TLS）能正常拿到 200。另外 curl 强制
    IPv4，能绕开部分站点 IPv6 不通导致的静默超时（山东就是这个症状）。
    """
    raw: bytes | None = None
    status = 0
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            status, raw = r.status, r.read()
    except Exception as py_err:
        try:
            import subprocess
            cp = subprocess.run(
                ["curl.exe", "-4", "-s", "-k", "-L", "--max-time", str(timeout),
                 "-A", UA["User-Agent"], "-w", "\n%{http_code}", url],
                capture_output=True, timeout=timeout + 10,
            )
            body = cp.stdout.rsplit(b"\n", 1)
            raw = body[0]
            status = int(body[1].strip() or 0) if len(body) > 1 else 0
            if raw is None or status == 0:
                raise py_err
        except Exception:
            raise py_err
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return status, raw, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return status, raw, raw.decode("utf-8", errors="replace")


def links(html: str, base: str) -> list[tuple[str, str]]:
    """抽出 (绝对URL, 锚文本)，跳过锚点与脚本。"""
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"""<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
                         html, re.S | re.I):
        href, text = m.group(1), m.group(2)
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", "", text)
        if text:
            out.append((urljoin(base, href), text))
    return out


def rank(text: str) -> tuple[int, bool, bool]:
    """给链接打分：同时含「分县」和「播种/粮食产量」的词才是目标表。"""
    county = any(h in text for h in COUNTY_HINTS)
    topic = any(h in text for h in TOPIC_HINTS)
    return int(county) + int(topic), county, topic


def is_volume(url: str, text: str, index_url: str) -> bool:
    """判断是否是一个年鉴卷次链接。

    两条判据取并集：锚文本里出现四位数年份，或 URL 走的是年鉴路径
    （``tjnj`` / ``nj/`` / ``indexch.htm``）。只靠锚文本会挑中「《XX统计年鉴
    2025》编印出版完成」这类新闻稿，踩过这个坑。
    """
    if url.rstrip("/") == index_url.rstrip("/"):
        return False
    if re.search(r"编印|出版|发行|征订|通知|公告", text):
        return False
    by_text = bool(re.search(r"20\d{2}", text))
    by_url = bool(re.search(r"(tjnj|/nj/|indexch\.htm|nj20\d{2})", url, re.I))
    return by_text or by_url


def frames(html: str, base: str) -> list[str]:
    """frameset 里的子框架地址——年鉴目录常靠它挂。"""
    out = []
    for m in re.finditer(r"""<(?:frame|iframe)\b[^>]*?src\s*=\s*["']([^"']+)["']""",
                         html, re.S | re.I):
        out.append(urljoin(base, m.group(1)))
    return out


def report(pairs: list[tuple[str, str]], label: str, cap: int = 20) -> int:
    """打印一批链接里的候选表，返回命中数。"""
    scored = sorted(((rank(t), u, t) for u, t in pairs), key=lambda x: -x[0][0])
    print(f"  {label}（含「分县/县市/县域」或「播种/粮食产量」）：")
    hit = 0
    for r, u, t in scored:
        if r[0] >= 1:
            flag = "★" if r[0] == 2 else " "
            print(f"    {flag} {t[:44]:44s} {u}")
            hit += 1
        if hit >= cap:
            break
    if hit == 0:
        print("    （无）")
    return hit


def probe(prov: str, depth: int, verbose: bool) -> None:
    name, url = PROVINCES[prov]
    print(f"[{name}] 索引页 {url}")
    try:
        status, raw, html = fetch(url)
    except Exception as e:  # 网络失败要显式报，不能静默当作「没有表」
        print(f"  !! 索引页取不到：{type(e).__name__}: {e}")
        return
    ls = links(html, url)
    print(f"  HTTP {status}  {len(raw)} B  {len(ls)} 个链接")

    # 第一层：年鉴卷次
    vols = [(u, t) for u, t in ls
            if re.search(r"(统计年鉴|年鉴)", t) and is_volume(u, t, url)]
    print(f"  卷次候选 {len(vols)} 个：")
    for u, t in vols[:12]:
        print(f"    - {t[:40]:40s} {u}")

    if not vols:
        # 没有卷次链接：把含县/播种的链接直接列出来，可能是扁平结构
        flat = [(u, t) for u, t in ls if rank(t)[0] >= 1]
        print(f"  无卷次结构，直接命中 {len(flat)} 个候选：")
        for u, t in flat[:15]:
            print(f"    - {t[:40]:40s} {u}")
        return

    if depth < 2:
        return

    # 第二层：进最新一卷，找分县表
    vu, vt = vols[0]
    print(f"\n  → 进入 {vt[:40]} {vu}")
    try:
        vs, vraw, vhtml = fetch(vu)
    except Exception as e:
        print(f"  !! 卷页取不到：{type(e).__name__}: {e}")
        return
    vl = links(vhtml, vu)
    fr = frames(vhtml, vu)
    print(f"  HTTP {vs}  {len(vraw)} B  {len(vl)} 个链接  {len(fr)} 个 frameset 子框架")

    hit = report(vl, "卷页直接命中")

    # 第三层：frameset / 目录页。标准年鉴（如 indexch.htm）用 frameset
    # 挂 left.htm(目录) + 正文，县级表在目录里。
    for fu in fr[:3]:
        print(f"\n  → frameset 子框架 {fu}")
        try:
            _, _, fhtml = fetch(fu)
        except Exception as e:
            print(f"  !! 取不到：{type(e).__name__}: {e}")
            continue
        fl = links(fhtml, fu)
        print(f"  {len(fl)} 个链接")
        hit += report(fl, "目录页命中")

    if hit == 0:
        print("\n  （全层无命中——卷页可能是 JS 渲染，或目录在更深一层，需人工看）")
    if verbose:
        print(f"\n  --- 卷页全部链接（前 {min(len(vl), 60)} 条）---")
        for u, t in vl[:60]:
            print(f"    {t[:44]:44s} {u}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--province", help="省份 key，见 --list")
    ap.add_argument("--depth", type=int, default=2, help="1=只看索引页, 2=再进最新一卷")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, (n, u) in PROVINCES.items():
            print(f"  {k:14s} {n}  {u}")
        return 0
    if not a.province:
        ap.print_help()
        return 2
    if a.province == "shanxi":
        print("山西走 scripts/sx_data/fetch_sx_sown.py（已验证，2005–2023 直链 xls）。")
        return 0
    if a.province not in PROVINCES:
        print(f"未知省份 {a.province}，用 --list 看可用值。")
        return 2
    probe(a.province, a.depth, a.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
