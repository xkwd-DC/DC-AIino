"""
山西县 冬小麦 生育期极端气候指数 (基于逐日原始 NASA POWER)。

输入: data/interim/nasapower_sx_daily_raw.parquet (county,adcode,date,tmax,tmin,prec,ws)
分组: 按"收获年"Y，冬小麦季 = 10月(Y-1) ~ 次年6月(Y)。
      (山西冬小麦: 10月播, 12-2月越冬, 3-4月返青拔节, 5-6月扬花灌浆, 6月中下旬收)
产出: data/interim/sx_wheat_extreme_index.parquet (县 x 收获年)

指数口径(ETCCDI 风格 + 冬小麦生育期适配):
  winter_cold_days   越冬冻害日数  12-2月 TMIN<=-10°C
  winter_tmin_min    越冬极端最低温 12-2月 TMIN 最低值(°C)
  spring_frost_days  晚霜冻日数    3-4月  TMIN<0°C
  spring_frost_late  拔节期晚霜    4月    TMIN<0°C 天数 (晚霜最伤穗)
  spring_cdd_max     春旱连续无雨   3-6月 最大连续无雨日(prec<1mm)
  spring_precip      春季降水       3-6月 累计降水(mm)  (越低越旱)
  grain_heat_days    灌浆期热害日数 5-6月 TMAX>=32°C
  grain_rain_days    灌浆期暴雨日数 5-6月 prec>=20mm (倒伏风险)
  sow_precip         播种期降水     10月(Y-1)累计降水(mm) (出苗/墒情)
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
IN = ROOT / "data" / "interim" / "nasapower_sx_daily_raw.parquet"
OUT = ROOT / "data" / "interim" / "sx_wheat_extreme_index.parquet"


def max_consec_dry(prec, thresh=1.0):
    dry = prec < thresh
    best = cur = 0
    for w in dry:
        cur = cur + 1 if w else 0
        best = max(best, cur)
    return best


def season_window(harvest_year):
    """冬小麦季: 10月(harvest-1) ~ 6月(harvest)。返回 (start, end) date 字符串。"""
    return (pd.Timestamp(harvest_year - 1, 10, 1),
            pd.Timestamp(harvest_year, 6, 30))


raw = pd.read_parquet(IN)
raw["date"] = pd.to_datetime(raw["date"])

recs = []
counties = raw.groupby("adcode")
for adcode, g in counties:
    g = g.sort_values("date")
    # 每个 adcode 对应的收获年 = 出现年份(从 2012 起)
    years = sorted(g["date"].dt.year.unique())
    harvest_years = [y for y in years if y >= 2012]
    for hy in harvest_years:
        s, e = season_window(hy)
        win = g[(g["date"] >= s) & (g["date"] <= e)]
        if win.empty:
            continue
        bymonth = win["date"].dt.month
        # 冬季 = 12月(Y-1) + 1-2月(Y)
        winter = win[((win["date"].dt.year == hy - 1) & (bymonth == 12)) |
                     ((win["date"].dt.year == hy) & (bymonth.isin([1, 2])))]
        spring = win[(win["date"].dt.year == hy) & (bymonth.isin([3, 4]))]
        spring_late = win[(win["date"].dt.year == hy) & (bymonth == 4)]
        spring_summer = win[(win["date"].dt.year == hy) & (bymonth.isin([3, 4, 5, 6]))]
        grain = win[(win["date"].dt.year == hy) & (bymonth.isin([5, 6]))]
        sow = win[(win["date"].dt.year == hy - 1) & (bymonth == 10)]

        recs.append({
            "county": g["county"].iloc[0], "adcode": adcode, "harvest_year": hy,
            "winter_cold_days": int((winter["tmin"] <= -10).sum()),
            "winter_tmin_min": round(float(winter["tmin"].min()), 2),
            "spring_frost_days": int((spring["tmin"] < 0).sum()),
            "spring_frost_late": int((spring_late["tmin"] < 0).sum()),
            "spring_cdd_max": max_consec_dry(spring_summer["prec"].values),
            "spring_precip": round(float(spring_summer["prec"].sum()), 1),
            "grain_heat_days": int((grain["tmax"] >= 32).sum()),
            "grain_rain_days": int((grain["prec"] >= 20).sum()),
            "sow_precip": round(float(sow["prec"].sum()), 1),
        })

out = pd.DataFrame(recs)
out.to_parquet(OUT, index=False)
print("落盘:", OUT, "| 行:", len(out), "| 县数:", out["adcode"].nunique(),
      "| 收获年:", out["harvest_year"].min(), "-", out["harvest_year"].max())
print(out.head(8).to_string(index=False))
