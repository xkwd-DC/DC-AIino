"""
用 NASA POWER 逐日 Tmax 算山西县 TX90p（相对极端高温，ETCCDI）。
- 县质心取点; 阈值 = 该县 2012-2023 生长季(4-9月)日最高温的 90 分位。
- 逐年: tx90p_days(生长季高于阈值日数) / tx90p_jja(6-8月) / tmax_max(年最高)。
产出: data/interim/tx90p_sx_county.csv
"""
import requests
import pandas as pd
import numpy as np
import time
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
cdf = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def fetch_tmax(lon, lat):
    p = {"parameters": "T2M_MAX", "community": "AG", "longitude": lon, "latitude": lat,
         "start": "20120101", "end": "20231231", "format": "JSON"}
    r = requests.get(URL, params=p, timeout=90)
    r.raise_for_status()
    d = r.json()["properties"]["parameter"]["T2M_MAX"]
    return pd.Series(list(d.values()),
                     index=pd.to_datetime(list(d.keys()), format="%Y%m%d"))


rows = []
for r in cdf.itertuples():
    try:
        s = fetch_tmax(r.lon, r.lat)
        gs_all = s[(s.index.month >= 4) & (s.index.month <= 9)]
        thr = float(np.nanpercentile(gs_all, 90))
        for y, g in s.groupby(s.index.year):
            gg = g[(g.index.month >= 4) & (g.index.month <= 9)]
            jja = g[(g.index.month >= 6) & (g.index.month <= 8)]
            rows.append({
                "county": r.county, "adcode": r.adcode, "year": int(y),
                "tx90p_thr": round(thr, 2), "tx90p_days": int((gg > thr).sum()),
                "tx90p_jja": int((jja > thr).sum()), "tmax_max": float(g.max()),
            })
    except Exception as e:
        print(f"  {r.county} 失败: {e}")
    time.sleep(0.4)

df = pd.DataFrame(rows)
out = ROOT / "data" / "interim" / "tx90p_sx_county.csv"
df.to_csv(out, index=False)
print("输出:", out, "| 行:", len(df))
print("tx90p_days 年度均值:")
print(df.groupby("year")["tx90p_days"].mean().round(2).to_string())
