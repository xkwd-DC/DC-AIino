"""
NASA POWER 逐日（免费免注册 API）→ 山西县日尺度极端气候因子。
参数: T2M(2m气温℃) T2MDEW(露点℃) PRECTOTCORR(降水mm/d) WS2M(2m风速m/s)。
目标变量（2012–2023 逐年，生长季4–9月为主）：
  heat_days       高温日数(Tmax>=35, 4-9月)
  heat_jja        关键期高温日数(6-8月, 玉米授粉/灌浆)
  rainstorm_days  暴雨日数(降水>=50mm, 4-9月)
  cdd_max         最大连续无雨日(降水<1mm, 4-9月, CDD)
  dry_hot_wind    干热风天数(Tmax>=32 & RH<=30 & WS2M>=3, 5-6月小麦)
  autumn_rain     秋淋/连阴雨=9-10月最大连续降水日(>=0.1mm)
产出: data/interim/nasapower_sx_daily_factors.parquet
"""
import requests
import pandas as pd
import numpy as np
import time
import math
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
cdf = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def rh_from_dew(t, td):
    """Magnus: 由气温与露点算相对湿度 (%)"""
    t = np.asarray(t, dtype=float); td = np.asarray(td, dtype=float)
    es = 6.112 * np.exp(17.67 * t / (t + 243.5))
    e = 6.112 * np.exp(17.67 * td / (td + 243.5))
    with np.errstate(divide='ignore', invalid='ignore'):
        rh = 100.0 * e / es
    rh = np.where(np.isfinite(rh), rh, np.nan)
    return np.clip(rh, 0, 100)


def max_consec_wet(prec, thresh=0.1):
    """最大连续雨日（>=thresh mm/日）"""
    wet = prec >= thresh
    best = cur = 0
    for w in wet:
        cur = cur + 1 if w else 0
        best = max(best, cur)
    return best


def max_consec_dry(prec, thresh=1.0):
    """最大连续无雨日（<thresh mm/日）——CDD"""
    dry = prec < thresh
    best = cur = 0
    for w in dry:
        cur = cur + 1 if w else 0
        best = max(best, cur)
    return best


def fetch(lon, lat):
    p = {"parameters": "T2M,T2MDEW,PRECTOTCORR,WS2M", "community": "AG",
         "longitude": lon, "latitude": lat,
         "start": "20120101", "end": "20231231", "format": "JSON"}
    r = requests.get(URL, params=p, timeout=90)
    r.raise_for_status()
    d = r.json()["properties"]["parameter"]
    idx = pd.to_datetime(list(d["T2M"].keys()), format="%Y%m%d")
    t2m = pd.Series(list(d["T2M"].values()), index=idx)
    tdew = pd.Series(list(d["T2MDEW"].values()), index=idx)
    prec = pd.Series(list(d["PRECTOTCORR"].values()), index=idx)
    ws = pd.Series(list(d["WS2M"].values()), index=idx)
    return pd.DataFrame({"tmax": t2m, "tdew": tdew, "prec": prec, "ws": ws})


rows = []
for r in cdf.itertuples():
    try:
        df = fetch(r.lon, r.lat)
        df["rh"] = rh_from_dew(df["tmax"], df["tdew"])
        df["month"] = df.index.month
        gs = df[(df.index.month >= 4) & (df.index.month <= 9)]
        for y, g in df.groupby(df.index.year):
            gs = g[(g.index.month >= 4) & (g.index.month <= 9)]
            heat = int((gs["tmax"] >= 35).sum())
            heat_jja = int((g[(g.index.month >= 6) & (g.index.month <= 8)]["tmax"] >= 35).sum())
            rainstorm = int((gs["prec"] >= 50).sum())
            cdd = max_consec_dry(gs["prec"].values)
            mjw = g[(g.index.month >= 5) & (g.index.month <= 6)]
            dhw = int(((mjw["tmax"] >= 32) & (mjw["rh"] <= 30) & (mjw["ws"] >= 3)).sum())
            sep_oct = g[(g.index.month >= 9) & (g.index.month <= 10)]
            autumnrain = max_consec_wet(sep_oct["prec"].values)
            rows.append({
                "county": r.county, "adcode": r.adcode, "year": int(y),
                "heat_days": heat, "heat_jja": heat_jja, "rainstorm_days": rainstorm,
                "cdd_max": cdd, "dry_hot_wind": dhw, "autumn_rain_days": autumnrain,
            })
    except Exception as e:
        print(f"  {r.county} 失败: {e}")
    time.sleep(0.4)
    print(f"  {r.county} 完成")

df = pd.DataFrame(rows)
out = ROOT / "data" / "interim" / "nasapower_sx_daily_factors.parquet"
df.to_parquet(out, index=False)
print("已输出:", out, "| 行:", len(df))
print(df.head(6).to_string(index=False))
