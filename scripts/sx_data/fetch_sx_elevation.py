"""
基于县质心用 OpenTopoData(srtm90m) 免登录查高程，产出 data/interim/sx_county_elevation.csv
"""
import pandas as pd
import requests, time
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
cdf = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")
API = "https://api.opentopodata.org/v1/srtm90m"

def batch(elems):
    loc = "|".join(f"{lat},{lon}" for lon, lat in elems)
    r = requests.get(API, params={"locations": loc}, timeout=60)
    r.raise_for_status()
    return r.json().get("results", [])

rows = []
pts = cdf[["lon", "lat"]].dropna().to_numpy()
# 每批 100 点
for i in range(0, len(pts), 100):
    chunk = [(float(lon), float(lat)) for lon, lat in pts[i:i + 100]]
    try:
        res = batch(chunk)
    except Exception as e:
        print("批", i, "失败:", e); res = [{"elevation": None} for _ in chunk]
    for (lon, lat), rr in zip(chunk, res):
        rows.append({
            "lon": lon, "lat": lat,
            "elev_m": (rr or {}).get("elevation"),
        })
    time.sleep(0.6)

el = pd.DataFrame(rows)
el.to_csv(ROOT / "data" / "interim" / "sx_county_elevation.csv", index=False)
print("高程获取:", len(el), " | 均值:", round(el["elev_m"].mean(), 1),
      "min:", el["elev_m"].min(), "max:", el["elev_m"].max())
