"""
山西县级 冬小麦(播种/产量/灌溉) 多年度面板。

逐年扫描《山西统计年鉴》online 县市篇 xls (20-XX)，用英文/中文表头稳健定位:
  - 播种表: 含 "Wheat" + "Sown"(或 播种面积)
  - 产量表: 含 "Wheat" + "Total Output"/"ton"(或 总产量)
  - 灌溉表: 含 "灌溉" + 面积
表结构(固定): col0=中文县名, col1=英文县名, 小麦列=表头出现"Wheat"的那一列。
数据年 xls 可机器读取: 2018-2023 (2014-2017 官网为 JPG, 需 OCR, 跳过)。
产出: data/interim/sx_wheat_panel.parquet (county, adcode?, year, wheat_sown_ha,
      wheat_output_t, wheat_yield_kgha, irrig_eff_kha)
"""
import urllib.request
import pandas as pd
import numpy as np
import io
import time
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
OUT = ROOT / "data" / "interim" / "sx_wheat_panel.parquet"
UA = {"User-Agent": "Mozilla/5.0"}
YEARS = list(range(2018, 2024))


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def read(url):
    return pd.read_excel(io.BytesIO(get(url)), header=None)


def head_text(df, nrows=12):
    return " | ".join(str(x) for x in df.iloc[:nrows].values.ravel())


def find_col(df, token):
    """返回表头(前8行)中出现 token 的列索引(取第一个)。"""
    for i in range(min(8, len(df))):
        for j in range(df.shape[1]):
            if token.lower() in str(df.iat[i, j]).lower():
                return j
    return None


def extract_county_val(df, val_col):
    """col0=县名, val_col=数值列 -> {county: value}。跳过空/表头/非数值行。"""
    d = {}
    for i in range(len(df)):
        name = df.iat[i, 0]
        if pd.isna(name) or not isinstance(name, str):
            continue
        name = str(name).strip()
        if not name or "Region" in name or "县(市" in name or any(c.isdigit() for c in name[:3]):
            continue
        v = df.iat[i, val_col]
        try:
            d[name] = float(v)
        except (TypeError, ValueError):
            continue
    return d


rows = []
for data_year in YEARS:
    nb = f"nj{data_year + 1}"
    sown = output = irrig = None
    for tno in range(3, 26):
        t = f"20-{tno:02d}"
        urls = [f"http://tjj.shanxi.gov.cn/tjsj/tjnj/{nb}/zk/html/{t}.xls",
                f"http://tjj.shanxi.gov.cn/tjsj/tjnj/{nb}/zk/html/{t}-0.xls"]
        df = None
        for url in urls:
            try:
                df = read(url)
                break
            except Exception:
                continue
        if df is None:
            continue
        txt = head_text(df)
        # 灌溉表
        if irrig is None and "灌溉" in txt:
            c = find_col(df, "灌溉")
            if c is not None:
                irrig = (df, c)
                continue
        # 小麦表(英文 Wheat 定位)
        if "Wheat" in txt:
            wc = find_col(df, "Wheat")
            if wc is None:
                continue
            if ("Total Output" in txt) or ("ton" in txt):
                if output is None:
                    output = (df, wc)
            elif ("Sown" in txt) or ("播种" in txt):
                if sown is None:
                    sown = (df, wc)
        if sown and output and irrig:
            break

    if not (sown and output):
        print(f"[{data_year}] 未找齐(播种={sown is not None},产量={output is not None},灌溉={irrig is not None})")
        continue

    s = extract_county_val(sown[0], sown[1])
    o = extract_county_val(output[0], output[1])
    ii = extract_county_val(irrig[0], irrig[1]) if irrig else {}
    common = set(s) & set(o)
    for name in common:
        if s[name] <= 0 or o[name] <= 0:
            continue
        rows.append({
            "county": name, "year": data_year,
            "wheat_sown_ha": round(s[name], 2),
            "wheat_output_t": round(o[name], 2),
            "wheat_yield_kgha": round(o[name] * 1000.0 / s[name], 1),
            "irrig_eff_kha": round(ii.get(name, np.nan), 2),
        })
    print(f"[{data_year}] 提取县数 {len(common)} | 播种表{t} 产量表{t} 灌溉表{t}")
    time.sleep(0.3)

panel = pd.DataFrame(rows)
panel.to_parquet(OUT, index=False)
print("\n落盘:", OUT, "| 行", len(panel), "| 县数", panel["county"].nunique() if len(panel) else 0,
      "| 年份", panel["year"].min() if len(panel) else "-", "-", panel["year"].max() if len(panel) else "-")
if len(panel):
    print("单产 中位", round(panel.wheat_yield_kgha.median(), 1),
          "| 范围", round(panel.wheat_yield_kgha.min(), 1), "-", round(panel.wheat_yield_kgha.max(), 1))
