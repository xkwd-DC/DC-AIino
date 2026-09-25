"""
抓取山西省县（区）级 geojson + 县质心（阿里 DataV，免登录）。
DataV 省级 _full 只到地级市，需按市 code 递归抓各市 _full 才能到县区。
产出: data/raw/geo/shanxi_county_full.json + data/interim/sx_county_centroids.csv
"""
import json
import requests
import pandas as pd
from shapely.geometry import shape
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
GEO = ROOT / "data" / "raw" / "geo"
GEO.mkdir(parents=True, exist_ok=True)
BASE = "https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json"


def get(code):
    r = requests.get(BASE.format(code=code), timeout=60)
    r.raise_for_status()
    return r.json()


# ① 省级 -> 地级市
prov = get("140000")
city_feats = prov.get("features", [])
print("省级 layer features:", len(city_feats))

# ② 各市 -> 县区；行政区级 1 级市可能也要 1-2 层，这里统一抓市下属
county_feats = []
city_codes = [f.get("properties", {}).get("adcode") for f in city_feats]
city_codes = [str(c) for c in city_codes if c]
for cc in city_codes:
    try:
        cc_gj = get(cc)
        sub = cc_gj.get("features", [])
        county_feats.extend(sub)
        print(f"  {cc}: {len(sub)} 县区")
    except Exception as e:
        print(f"  {cc} 抓取失败: {e}")

out = GEO / "shanxi_county_full.json"
out.write_text(json.dumps({"type": "FeatureCollection", "features": county_feats},
                          ensure_ascii=False), encoding="utf-8")
print("县区 geojson 已存:", out, "| features:", len(county_feats))

rows = []
for f in county_feats:
    p = f.get("properties", {})
    name = p.get("name")
    code = p.get("adcode")
    center = p.get("center")
    try:
        c = shape(f.get("geometry")).representative_point()
        lon, lat = c.x, c.y
    except Exception:
        lon, lat = (center[0], center[1]) if center else (None, None)
    rows.append({"county": name, "adcode": code, "lon": lon, "lat": lat})

df = pd.DataFrame(rows)
df.to_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv", index=False)
print("县质心:", len(df), "个")
print(df.head(10).to_string(index=False))
