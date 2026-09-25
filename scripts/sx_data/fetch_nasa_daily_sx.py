"""
NASA POWER 逐日(免费免注册) -> 山西县 逐日原始序列落盘。

目的: 现有 nasapower_sx_daily_factors 只存了压缩后的"通用 4-9 月"指数，
且未取 T2M_MIN(拿不到霜冻/极寒)。冬小麦需要按生育期窗口的极端指数，
因此先把逐日原始 (T2M_MAX/T2M_MIN/PRECTOTCORR/WS2M) 落盘，后续可任意重算。

区间: 2011-10-01 -> 2024-12-31 (覆盖 2012-2024 各季冬小麦 10月播-次年6月收)。
产出: data/interim/nasapower_sx_daily_raw.parquet
格式: county, adcode, date, tmax, tmin, prec, ws  (长表)
"""
import requests
import pandas as pd
import time
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
OUT = ROOT / "data" / "interim" / "nasapower_sx_daily_raw.parquet"
cdf = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "T2M_MAX,T2M_MIN,PRECTOTCORR,WS2M"


def fetch(lon, lat):
    p = {"parameters": PARAMS, "community": "AG", "longitude": lon,
         "latitude": lat, "start": "20111001", "end": "20241231", "format": "JSON"}
    r = requests.get(URL, params=p, timeout=90)
    r.raise_for_status()
    d = r.json()["properties"]["parameter"]
    idx = pd.to_datetime(list(d["T2M_MAX"].keys()), format="%Y%m%d")
    tmax = pd.Series(list(d["T2M_MAX"].values()), index=idx)
    tmin = pd.Series(list(d["T2M_MIN"].values()), index=idx)
    prec = pd.Series(list(d["PRECTOTCORR"].values()), index=idx)
    ws = pd.Series(list(d["WS2M"].values()), index=idx)
    return pd.DataFrame({"tmax": tmax, "tmin": tmin, "prec": prec, "ws": ws})


blocks = []
for r in cdf.itertuples():
    try:
        df = fetch(r.lon, r.lat)
        df = df.reset_index().rename(columns={"index": "date"})
        df["county"] = r.county
        df["adcode"] = r.adcode
        blocks.append(df)
        print(f"  {r.county} ({r.adcode}) OK, {len(df)}days")
    except Exception as e:
        print(f"  {r.county} ({r.adcode}) 失败: {e}")
    time.sleep(0.4)

raw = pd.concat(blocks, ignore_index=True)
raw.to_parquet(OUT, index=False)
print("\n落盘:", OUT, "| 行:", len(raw), "| 县数:", raw["adcode"].nunique())
print("年份范围:", raw["date"].min().date(), "->", raw["date"].max().date())
print(raw.head(4).to_string(index=False))
