"""
山西县级 冬小麦 单产 + 有效灌溉面积 提取 (2023 冒烟/单一数据年)。

《山西统计年鉴》online 县市篇表(列位置固定, 顶部英文副标题可稳健定位):
  20-07 主要粮食作物播种面积:  county(0), 英文(1), ... 小麦(5=播种面积 公顷 ha)
  20-08 主要粮食作物产量:      county(0), 英文(1), ... 小麦(5=总产量 吨)
  20-14 农业生产条件:          county(0), 年末有效灌溉面积(2, 千公顷)

单产  kg/ha  = 总产量(吨)*1000 / 播种面积(公顷)
注: 仅做 xx年 的冒烟验证, 后续扩到 2018-2023 by 逐年定位同构表。
"""
import urllib.request
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
UA = {"User-Agent": "Mozilla/5.0"}
BASE = "http://tjj.shanxi.gov.cn/tjsj/tjnj/nj2024/zk/html/"   # 数据年 2023


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def read(tbl):
    df = pd.read_excel(__import__("io").BytesIO(get(BASE + tbl + ".xls")), header=None)
    df = df.map(lambda x: np.nan if str(x).strip() in ("nan", "") else x)
    return df


def extract_county_wheat(df):
    """从15列同构表(播种/产量)提取 county(0) + 小麦(5)。返回 name->(adcode0, wheat)。"""
    out = []
    for i in range(len(df)):
        name = df.iat[i, 0]
        if pd.isna(name) or not isinstance(name, str):
            continue
        name = str(name).strip()
        if not name or name in ("县(市、区)",):
            continue
        if any(c.isdigit() for c in name):       # 跳过合计/数字行
            continue
        v = df.iat[i, 5]
        if pd.isna(v):
            continue
        out.append((name, float(v)))
    return out


sown = extract_county_wheat(read("20-07"))       # 小麦播种面积 千公顷
outp = extract_county_wheat(read("20-08"))       # 小麦总产量 吨
irr = read("20-14")

# 灌溉: county(0) + 有效灌溉面积(2 千公顷)
irr_list = []
for i in range(len(irr)):
    name = irr.iat[i, 0]
    if pd.isna(name) or not isinstance(name, str):
        continue
    name = str(name).strip()
    if not name or name == "县(市、区)" or any(c.isdigit() for c in name):
        continue
    v = irr.iat[i, 2]
    if not pd.isna(v):
        irr_list.append((name, float(v)))

s = dict(sown); o = dict(outp); ii = dict(irr_list)
rows = []
for name, sown_kha in sown:
    if name not in o or name not in ii:
        continue
    out_t = o[name]
    if out_t <= 0 or sown_kha <= 0:
        continue
    rows.append({
        "county": name, "data_year": 2023,
        "wheat_sown_ha": round(sown_kha, 2),
        "wheat_output_t": round(out_t, 2),
        "wheat_yield_kgha": round(out_t * 1000.0 / sown_kha, 1),   # 千克/公顷
        "irrig_eff_kha": round(ii[name], 2),
    })

panel = pd.DataFrame(rows).sort_values("wheat_yield_kgha", ascending=False)
out = ROOT / "data" / "interim" / "sx_wheat_2023_smoke.parquet"
panel.to_parquet(out, index=False)

print("2023 县级冬小麦提取(冒烟): 县数", len(panel))
print("单产统计: min", round(panel.wheat_yield_kgha.min(), 1),
      "| 中位", round(panel.wheat_yield_kgha.median(), 1),
      "| max", round(panel.wheat_yield_kgha.max(), 1))
print("有效灌溉面积(千公顷)范围:", round(panel.irrig_eff_kha.min(), 2), "~",
      round(panel.irrig_eff_kha.max(), 2))
print("\nTop 12 单产县:")
print(panel.head(12).to_string(index=False))
print("\n高灌溉率县(灌溉/播种 比值 top8):")
panel["irr_ratio"] = panel.irrig_eff_kha * 1000.0 / panel.wheat_sown_ha
print(panel.sort_values("irr_ratio", ascending=False).head(8).to_string(index=False))
