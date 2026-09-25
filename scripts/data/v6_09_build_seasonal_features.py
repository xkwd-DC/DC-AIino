#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 9：从 TerraClimate 月度网构构建**生长季窗口 + 月度尺度极端/季节指数**。

问题背景：
  现行 v6 面板的 temp/prec/sun 是**年度**聚合（均/和），丢失生长季(4-9月)窗口与
  极端事件信号。TerraClimate 为**月度**分辨率（12 步/年），故「极端指数」按月度尺度
  构造（科学上成立的上限）：
    · 生长季聚合：gs_temp(均温)、gs_prec(降水总和)、gs_srad(辐射均值)
    · 生长季强度：gdd10(积温,基温10°C,月度近似)、gs_pet(参照蒸散和)、
                   gs_aridity(PET/降水, 生长季干旱强度)
    · 生长季明显性/极端：gs_tmax_mean、gs_tmin_mean
    · 降水集中度：prec_cv(月降水变异系数)、max_month_prec(最湿月降水/年降水)
    · 季节对比：winter_temp(12-2月均温), 生长季-冬季温差

口径：县治最近格点代表县域气象（与 v6_01c 一致）；未做日级指数（无该数据源）。

输出: data/interim/paper_panel_v7_prediction.parquet
（在原 v6 climate_full 基础上追加 gs_* / gdd10 / prec_* / winter_temp 等列）
"""
import logging
import sys
from pathlib import Path

import h5py  # backend venv 用 h5py 读 NetCDF-4；主 venv(netCDF4) 启动器已坏
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6_climate_full.parquet"
NC_DIR = PROJECT_ROOT / "data" / "raw" / "terraclimate"
OUT = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"

VARS = ["tmax", "tmin", "ppt", "srad", "pet"]
YEARS = range(2012, 2024)
GS = [3, 4, 5, 6, 7, 8]    # Apr(3)..Sep(8)  生长季
WINTER = [11, 0, 1]        # Dec(11),Jan(0),Feb(1)


def _read_var(year: int, var: str, j0: int, j1: int, i0: int, i1: int,
              jj, ii) -> np.ndarray:
    """读单年单变量的月度网构，统一 scale/offset，返回 (12, n_counties)。"""
    fp = NC_DIR / f"TerraClimate_{var}_{year}.nc"
    with h5py.File(fp, "r") as f:
        ds = f[var]
        attrs = ds.attrs
        scale = float(attrs.get("scale_factor", 1.0))
        offset = float(attrs.get("add_offset", 0.0))
        fill = attrs.get("_FillValue", None)
        fillv = -32768 if fill is None else np.asarray(fill).ravel()[0]
        data = np.asarray(ds[:, j0:j1, i0:i1], dtype=np.float64)
    data = data * scale + offset
    data[data <= (fillv * scale + offset)] = np.nan
    vals = data[:, jj, ii]          # (12, n_counties)
    return vals


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    panel = pd.read_parquet(SRC_PANEL)
    # 县唯一坐标（用于最近格点映射）—— 用 v6 climate_full 已有的 lon/lat
    coord = panel[["区县代码", "lon", "lat"]].drop_duplicates("区县代码").dropna(subset=["lon", "lat"]).reset_index(drop=True)
    logging.info("counties with lon/lat: %d", len(coord))

    # 参考网格（以 2012 tmax 为准）
    with h5py.File(NC_DIR / "TerraClimate_tmax_2012.nc", "r") as f:
        lat = np.asarray(f["lat"][:], dtype=float)
        lon = np.asarray(f["lon"][:], dtype=float)
    nj, ni = len(lat), len(lon)
    lat_asc = lat if lat[0] < lat[-1] else lat[::-1]

    plon, plat = coord["lon"].values.astype(float), coord["lat"].values.astype(float)
    j = np.clip(np.searchsorted(lat_asc, plat), 1, nj - 1)
    j = np.where(np.abs(lat_asc[j] - plat) <= np.abs(lat_asc[j - 1] - plat), j, j - 1)
    if lat[0] > lat[-1]:
        j = nj - 1 - j
    i = np.clip(np.searchsorted(lon, plon), 1, ni - 1)
    i = np.where(np.abs(lon[i] - plon) <= np.abs(lon[i - 1] - plon), i, i - 1)
    # 中国窗口
    j0 = (nj - 1 - int(np.searchsorted(lat_asc, 60.0)), nj - 1 - int(np.searchsorted(lat_asc, 10.0))) if lat[0] > lat[-1] \
        else (int(np.searchsorted(lat_asc, 10.0)), int(np.searchsorted(lat_asc, 60.0)))
    i0 = int(np.searchsorted(lon, 65.0)); i1 = int(np.searchsorted(lon, 145.0))
    jj, ii = j - j0[0], i - i0
    logging.info("window rows %d x cols %d, counties mapped=%d", j0[1] - j0[0], i1 - i0, len(coord))

    cid = coord["区县代码"].values.astype(int)
    # 逐变量逐月累积 (12, n_c) → 全年
    mon = {v: {} for v in VARS}
    for year in YEARS:
        for var in VARS:
            vals = _read_var(year, var, j0[0], j0[1], i0, i1, jj, ii)   # (12, n_c)
            mon[var][year] = vals
        logging.info("read %s x 12 vars done", year)

    # 构建县×年面板
    rows = []
    for year in YEARS:
        for var in VARS:
            arr = mon[var][year]          # (12, n_c)
            for k, cc in enumerate(cid):
                rows.append({"区县代码": cc, "年份": year, "var": var,
                             **{f"m{m+1}": arr[m, k] for m in range(12)}})
    wide = pd.DataFrame(rows)
    logging.info("wide monthly done: %s", wide.shape)

    # 透视：每县×年 × 变量 → 用汇总函数
    feats = []
    for var in VARS:
        sub = wide[wide["var"] == var]
        # 年度聚合（与 v6 逐口径对齐，便于一致性检查）
        sub["annual"] = sub[[f"m{m+1}" for m in range(12)]].sum(axis=1) if var in ("ppt", "pet") \
            else sub[[f"m{m+1}" for m in range(12)]].mean(axis=1)
        feats.append(sub[["区县代码", "年份", "annual"]].rename(columns={"annual": f"annual_{var}"}))
    annual = feats[0]
    for f in feats[1:]:
        annual = annual.merge(f, on=["区县代码", "年份"], how="outer")

    # 生长季聚合 & 指数 —— 逐行计算
    gs_rows = []
    for var in VARS:
        sub = wide[wide["var"] == var]
        m = np.array([f"m{i+1}" for i in GS])
        if var in ("ppt", "pet"):
            gs = sub[m].sum(axis=1)
        else:
            gs = sub[m].mean(axis=1)
        tmp = sub[["区县代码", "年份"]].copy()
        tmp[f"gs_{var}"] = gs
        gs_rows.append(tmp)
    gs = gs_rows[0]
    for g in gs_rows[1:]:
        gs = gs.merge(g, on=["区县代码", "年份"], how="outer")
    gs = gs.rename(columns={"gs_tmax": "gs_tmax_mean", "gs_tmin": "gs_tmin_mean"})

    # 扩展指数
    extra = wide[wide["var"] == "ppt"].copy()
    m_all = [f"m{m+1}" for m in range(12)]
    pm = np.array(extra[m_all])
    extra["prec_cv"] = np.nanstd(pm, axis=1) / (np.nanmean(pm, axis=1) + 1e-6)
    extra["max_month_prec_share"] = np.nanmax(pm, axis=1) / (np.nansum(pm, axis=1) + 1e-6)
    gs_m = [f"m{i+1}" for i in GS]
    extra["gs_prec_share"] = np.nansum(np.array(extra[gs_m]), axis=1) / (np.nansum(pm, axis=1) + 1e-6)

    # 冬季温度（tmean 用 (tmax+tmin)/2），温差 = 生长季-冬季
    def season_temp(var):
        sub = wide[wide["var"] == var]
        val = sub[[f"m{i+1}" for i in WINTER]].mean(axis=1)
        t = sub[["区县代码", "年份"]].copy()
        t[f"winter_{var}"] = val
        return t
    wtmax = season_temp("tmax"); wtmin = season_temp("tmin")
    winter = wtmax.merge(wtmin, on=["区县代码", "年份"])
    winter["winter_temp"] = (winter["winter_tmax"] + winter["winter_tmin"]) / 2

    # 合并全部县×年特征
    out = annual.copy()
    out = out.merge(gs, on=["区县代码", "年份"])
    # gdd10（生长季积温，基温 10°C，月度近似：月均温>10 则累加 (mean-10)*天数）
    tavg_gs = (gs["gs_tmax_mean"] + gs["gs_tmin_mean"]) / 2
    days_gs = 183  # Apr-Sep 近似 183 天
    out["gdd10"] = np.maximum(tavg_gs - 10, 0) * days_gs
    out["gs_aridity"] = out["gs_pet"] / (out["gs_ppt"] + 1e-6)
    out = out.merge(extra[["区县代码", "年份", "prec_cv", "max_month_prec_share", "gs_prec_share"]],
                    on=["区县代码", "年份"], how="left")
    out = out.merge(winter[["区县代码", "年份", "winter_temp"]], on=["区县代码", "年份"], how="left")
    out["seasonal_temp_range"] = gs["gs_tmax_mean"].values - out["winter_temp"].values if len(out) == len(gs) else np.nan

    # 附上 v6 已有列（temp/prec/sun/ndvi/.../log_yield/单产）
    base = panel.drop(columns=["temp", "prec", "sun"], errors="ignore")  # 保留 log_yield 等
    merged = base.merge(out, on=["区县代码", "年份"], how="left")
    # 用新算的 annual_tmax/tmin 合成 temp 以保持同口径
    merged["temp"] = (merged["annual_tmax"] + merged["annual_tmin"]) / 2
    merged["prec"] = merged["annual_ppt"]
    merged["sun"] = merged["annual_srad"]

    merged.to_parquet(OUT, index=False)
    logging.info("✅ 写入 %s (%s)", OUT.name, merged.shape)
    cols = [c for c in merged.columns if c.startswith(("gs_", "gdd", "prec_", "max_month", "winter", "seasonal", "annual_"))]
    logging.info("新增特征: %s", cols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
