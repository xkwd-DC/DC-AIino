"""
下载并解析《山西统计年鉴》在线版"县市篇·主要粮食作物播种面积"表。
产出 data/interim/sx_sown/<data_year>.csv  (county, grain_sown_ha)

注：2014-2017 数据年在官网为 .jpg 扫描图(需OCR)，本脚本跳过并记录。
"""
import io
import os
import re
import urllib.request
import pandas as pd
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
OUT_DIR = ROOT / "data" / "interim" / "sx_sown"
RAW_DIR = ROOT / "data" / "raw" / "sx_yearbook"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0"}

# 山西 11 个地级市/地区名(用于识别表内的"城市合计"行)
PRECITY = {"太原市","大同市","阳泉市","长治市","晋城市","朔州市",
           "晋中市","运城市","忻州市","临汾市","吕梁市",
           "忻州地区","吕梁地区","晋中地区","临汾地区","运城地区","阳泉地区"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


# data_year -> (type, url)  type in {xls, htm}
PLAN = {
    2005: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2006/book/18-8.htm"),
    2006: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2007/book/18-7.htm"),
    2007: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2008/book/18-8.htm"),
    2008: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2009/book/18-10.htm"),
    2009: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2010/book/19-12.htm"),
    2010: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2011/book/19-9.Htm"),
    2011: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2012/book/19-9.Htm"),
    2012: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2013/book/19-9.htm"),
    2013: ("htm", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2014/book/20-11.htm"),
    2018: ("xls", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2019/zk/html/20-10.xls"),
    2019: ("xls", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2020/zk/html/20-10-0.xls"),
    2020: ("xls", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2021/zk/html/20-07.xls"),
    2021: ("xls", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2022/zk/html/20-07.xls"),
    2022: ("xls", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2023/zk/html/20-07.xls"),
    2023: ("xls", "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2024/zk/html/20-07.xls"),
}


def strip_ws(s):
    return re.sub(r"\s+", "", str(s)) if s is not None else ""


def parse_xls(data: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(data), engine="xlrd", header=None)
    rows = []
    cur_city = ""
    for i in range(len(df)):
        name = strip_ws(df.iloc[i, 0])
        if (not name) or ("播种" in name) or ("单位" in name) \
                or ("SOWN" in name.upper()) or ("REGION" in name.upper()) \
                or ("(" in name) or not re.search(r"[\u4e00-\u9fff]", name):
            continue
        grain = df.iloc[i, 2]
        try:
            grain = float(grain)
        except Exception:
            continue
        if name in PRECITY:              # 城市合计行, 记下当前城市
            cur_city = name
            continue
        if not (grain > 0):
            continue
        rows.append({"city": cur_city, "county": name, "grain_sown_ha": grain})
    return pd.DataFrame(rows)


def parse_htm(data: bytes) -> pd.DataFrame:
    txt = data.decode("gbk", errors="replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", txt, re.S)
    # 解析每行 cells
    parsed = []
    for r in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)
        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", "").replace("&NBSP;", "") for c in cells]
        parsed.append(cells)

    # 找 main 表头行(某单元格含"县"且含"市/区")
    hdr_idx = None
    for i, cells in enumerate(parsed):
        if any(("县" in c) and (("市" in c) or ("区" in c)) for c in cells):
            hdr_idx = i
            break
    if hdr_idx is None:
        return pd.DataFrame()

    # grain_col = main 表头行里最靠左含"粮食"的列
    grain_col = None
    for j, c in enumerate(parsed[hdr_idx]):
        if "粮食" in c:
            grain_col = j
            break
    if grain_col is None:
        return pd.DataFrame()

    # 单位
    unit = "公顷"
    if "千公顷" in txt or "千 公顷" in txt:
        unit = "千公顷"
    mult = 1000.0 if unit == "千公顷" else 1.0

    out = []
    cur_city = ""
    for cells in parsed:
        if grain_col >= len(cells):
            continue
        name = strip_ws(cells[0])
        if not name or name in ("县市", "Region"):
            continue
        if name in PRECITY:              # 城市合计行
            cur_city = name
            continue
        grain = cells[grain_col].replace(",", "")
        try:
            grain = float(grain)
        except Exception:
            continue
        if grain > 0:
            out.append({"city": cur_city, "county": name, "grain_sown_ha": grain * mult})
    return pd.DataFrame(out)


summary = {}
for data_year, (typ, url) in PLAN.items():
    dest = RAW_DIR / f"{data_year}_sown.{typ}"
    try:
        data = fetch(url)
        open(dest, "wb").write(data)
        df = parse_xls(data) if typ == "xls" else parse_htm(data)
        df["data_year"] = data_year
        out = OUT_DIR / f"{data_year}.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        summary[data_year] = {"n": len(df), "file": str(out)}
        print(f"data{data_year}: {len(df)} rows -> {out.name}")
    except Exception as e:
        summary[data_year] = {"error": str(e)}
        print(f"data{data_year}: ERROR {e}")

print("\n=== summary ===")
for k, v in summary.items():
    print(k, v)
