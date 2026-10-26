"""M08 国外模式：GeoJSON 单元中心点 → TerraClimate 月度栅格 → 生长季特征。

两个必须记住的坑
================
1. netCDF4 的 `v[:, jj, ii]` 是**外积**（每个 j 配每个 i），不是点对点。
   这里改成按瓦片读窗口再在窗口内取点，避免把 (n, n) 当 (n,)。
2. TerraClimate 的 lat 是**降序**（90 → -90），算索引前必须翻转。

覆盖窗口：本地只落了 2012-2023 年，超出范围不做插值、不做外推。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services import panel_cleaner

BACKEND_DIR = Path(__file__).resolve().parents[1]
NC_DIR = BACKEND_DIR.parent / "data" / "raw" / "terraclimate"
VARS = ("tmax", "tmin", "ppt", "srad", "pet")


class ClimateUnavailable(panel_cleaner.CleanError):
    """当前环境读不了 NetCDF（沙箱缺 DLL / 文件缺失）。"""


def available_years() -> list[int]:
    years: set[int] = set()
    for item in NC_DIR.glob("TerraClimate_tmax_*.nc"):
        try:
            years.add(int(item.stem.rsplit("_", 1)[-1]))
        except ValueError:
            continue
    return sorted(years)


def _ring_area(ring: list[list[float]]) -> float:
    """鞋带公式：返回有符号面积（用于挑 MultiPolygon 的主面）。"""
    if len(ring) < 3:
        return 0.0
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += x1 * y2 - x2 * y1
    return total / 2


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """多边形面积质心；退化环退回到顶点均值。"""
    area = _ring_area(ring)
    if abs(area) < 1e-12:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    cx = cy = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    factor = 1 / (6 * area)
    return (cx * factor, cy * factor)


def _unit_from_geometry(geom: dict[str, Any]) -> tuple[float, float] | None:
    kind = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None
    if kind == "Polygon":
        rings = [coords[0]]
    elif kind == "MultiPolygon":
        rings = [poly[0] for poly in coords if poly]
    else:
        return None
    if not rings:
        return None
    largest = max(rings, key=lambda r: abs(_ring_area(r)))
    return _ring_centroid(largest)


_NAME_KEYS = (
    "name", "NAME", "Name", "name_zh", "NAME_ZH", "NAME_1", "NAME_2",
    "county", "region", "district", "admin", "ADM2_ZH", "ADM1_ZH",
)
_CODE_KEYS = ("code", "CODE", "id", "ID", "adcode", "ADCODE", "iso_3166_2")


def _pick(props: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = props.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return None


def parse_geojson(path: Path) -> list[dict[str, Any]]:
    """返回 [{name, code, lon, lat}]。只取主面质心，不做面内均值。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        payload = json.loads(path.read_text(encoding="gbk"))
    except json.JSONDecodeError as exc:
        raise panel_cleaner.CleanError(f"GeoJSON 解析失败：{exc}") from exc

    if payload.get("type") == "FeatureCollection":
        features = payload.get("features") or []
    elif payload.get("type") == "Feature":
        features = [payload]
    else:
        raise panel_cleaner.CleanError("GeoJSON 必须是 FeatureCollection 或 Feature")

    units: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        props = feature.get("properties") or {}
        center = _unit_from_geometry(feature.get("geometry") or {})
        if center is None:
            continue
        name = _pick(props, _NAME_KEYS) or f"unit_{index + 1}"
        units.append(
            {
                "name": name,
                "code": _pick(props, _CODE_KEYS),
                "lon": round(center[0], 4),
                "lat": round(center[1], 4),
                "index": len(units),
            }
        )
    if not units:
        raise panel_cleaner.CleanError(
            "GeoJSON 里没有可用的面要素（只支持 Polygon / MultiPolygon）"
        )
    return units


def _open_var(var: str, year: int):
    try:
        import netCDF4  # 延迟导入：沙箱里 DLL 会失败，真实环境正常
    except Exception as exc:  # noqa: BLE001 - 需要把任何导入失败降级成可读错误
        raise ClimateUnavailable(
            "当前环境无法读取 NetCDF（netCDF4 初始化失败），国外模式不可用"
        ) from exc
    path = NC_DIR / f"TerraClimate_{var}_{year}.nc"
    if not path.exists():
        raise ClimateUnavailable(f"缺少气候栅格：TerraClimate_{var}_{year}.nc")
    return netCDF4.Dataset(path), path


def _grid_axes() -> tuple[np.ndarray, np.ndarray]:
    ds, _ = _open_var("tmax", available_years()[0])
    try:
        lat = np.asarray(ds["lat"][:], dtype=float)
        lon = np.asarray(ds["lon"][:], dtype=float)
    finally:
        ds.close()
    return lat, lon


def _to_index(axis: np.ndarray, values: np.ndarray, ascending: bool) -> np.ndarray:
    if not ascending:
        flipped = axis[::-1]
        idx = np.searchsorted(flipped, values)
        idx = np.clip(idx, 0, len(flipped) - 1)
        return len(axis) - 1 - idx
    idx = np.searchsorted(axis, values)
    return np.clip(idx, 0, len(axis) - 1)


def _read_tiles(
    var: str, year: int, jj: np.ndarray, ii: np.ndarray, tile: int = 720
) -> np.ndarray:
    """按瓦片读窗口，返回 (12, n_points)。瓦片 720 格 ≈ 30°。"""
    n = len(jj)
    out = np.full((12, n), np.nan)
    ds, _ = _open_var(var, year)
    try:
        data = ds[var]
        data.set_auto_mask(False)
        tiles: dict[tuple[int, int], list[int]] = {}
        for k in range(n):
            tiles.setdefault((int(jj[k]) // tile, int(ii[k]) // tile), []).append(k)
        for (tj, ti), members in tiles.items():
            j0, i0 = tj * tile, ti * tile
            j1, i1 = min(j0 + tile, data.shape[1]), min(i0 + tile, data.shape[2])
            block = np.asarray(data[:, j0:j1, i0:i1])
            for k in members:
                out[:, k] = block[:, int(jj[k]) - j0, int(ii[k]) - i0]
    finally:
        ds.close()
    return out


def _features(monthly: dict[str, np.ndarray], lat: float) -> dict[str, float]:
    """monthly[var] 是长度 12 的数组。生长季按半球翻转。"""
    gs = [3, 4, 5, 6, 7, 8] if lat >= 0 else [9, 10, 11, 0, 1, 2]
    winter = [m for m in range(12) if m not in gs]

    def take(var: str, months: list[int], how: str) -> float:
        values = np.asarray(monthly[var])[months]
        return float(np.nansum(values) if how == "sum" else np.nanmean(values))

    annual_tmax = take("tmax", list(range(12)), "mean")
    annual_tmin = take("tmin", list(range(12)), "mean")
    annual_ppt = take("ppt", list(range(12)), "sum")
    annual_srad = take("srad", list(range(12)), "mean")

    gs_tmax = take("tmax", gs, "mean")
    gs_tmin = take("tmin", gs, "mean")
    gs_ppt = take("ppt", gs, "sum")
    gs_srad = take("srad", gs, "mean")
    gs_pet = take("pet", gs, "sum")

    tavg_gs = (gs_tmax + gs_tmin) / 2
    gdd10 = max(tavg_gs - 10.0, 0.0) * len(gs) * 30.5

    ppt_all = np.asarray(monthly["ppt"], dtype=float)
    prec_cv = float(np.nanstd(ppt_all) / (np.nanmean(ppt_all) + 1e-6))
    gs_prec_share = float(np.nansum(ppt_all[gs]) / (np.nansum(ppt_all) + 1e-6))

    winter_temp = float(
        (take("tmax", winter, "mean") + take("tmin", winter, "mean")) / 2
    )
    return {
        "gs_tmax_mean": gs_tmax,
        "gs_tmin_mean": gs_tmin,
        "gs_ppt": gs_ppt,
        "gs_srad": gs_srad,
        "gs_pet": gs_pet,
        "gdd10": gdd10,
        "gs_aridity": float(gs_pet / (gs_ppt + 1e-6)),
        "prec_cv": prec_cv,
        "gs_prec_share": gs_prec_share,
        "winter_temp": winter_temp,
        "seasonal_temp_range": float(gs_tmax - winter_temp),
        "spei_growing_season_mean": float("nan"),
        "temp": (annual_tmax + annual_tmin) / 2,
        "prec": annual_ppt,
        "sun": annual_srad,
    }


def build_climate(units: list[dict[str, Any]], years: list[int]) -> pd.DataFrame:
    """对给定单元与年份批量取气候。返回 unit_index × year 的长表。"""
    if not units or not years:
        return pd.DataFrame()
    lat_axis, lon_axis = _grid_axes()
    lats = np.array([u["lat"] for u in units], dtype=float)
    lons = np.array([u["lon"] for u in units], dtype=float)
    jj = _to_index(lat_axis, lats, ascending=bool(lat_axis[0] < lat_axis[-1]))
    ii = _to_index(lon_axis, lons, ascending=bool(lon_axis[0] < lon_axis[-1]))

    rows: list[dict[str, Any]] = []
    for year in years:
        monthly = {var: _read_tiles(var, year, jj, ii) for var in VARS}
        for k, unit in enumerate(units):
            values = {var: monthly[var][:, k] for var in VARS}
            rows.append(
                {
                    "unit_index": unit["index"],
                    "year": year,
                    **_features(values, float(unit["lat"])),
                }
            )
    return pd.DataFrame(rows)


def _norm(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "")


def attach_climate_custom(
    df: pd.DataFrame, geo_path: Path
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """把上传表按地区名/代码对到 GeoJSON 单元，再回填气候。"""
    units = parse_geojson(geo_path)
    by_name = {_norm(u["name"]): u for u in units}
    by_code = {_norm(u["code"]): u for u in units if u.get("code")}

    codes: list[Any] = []
    names: list[Any] = []
    idxs: list[Any] = []
    for row in df.itertuples():
        name_raw = getattr(row, "region_name", None)
        code_raw = getattr(row, "region_code", None)
        has_code = isinstance(code_raw, str) and code_raw.strip() != ""
        unit = by_code.get(_norm(code_raw)) if has_code else None
        if unit is None and isinstance(name_raw, str) and name_raw.strip():
            unit = by_name.get(_norm(name_raw))
        codes.append(unit["code"] if unit and unit.get("code") else pd.NA)
        names.append(unit["name"] if unit else pd.NA)
        idxs.append(unit["index"] if unit else pd.NA)

    out = df.copy()
    out["matched_code"] = codes
    out["matched_county"] = names
    out["matched_province"] = pd.NA
    out["matched_city"] = pd.NA
    out["match_method"] = ["geojson" if pd.notna(i) else "unmatched" for i in idxs]
    out["match_note"] = ""
    out["_unit_index"] = pd.array(idxs, dtype="Int64")

    years = sorted({int(y) for y in out["year"].dropna().unique()})
    wanted = [u for u in units if u["index"] in set(out["_unit_index"].dropna())]
    climate = build_climate(wanted, years)
    merged = out.merge(
        climate, left_on=["_unit_index", "year"], right_on=["unit_index", "year"],
        how="left",
    ).drop(columns=["unit_index"], errors="ignore")
    merged["climate_available"] = merged["gs_tmax_mean"].notna()

    total = len(merged)
    hit = int(merged["_unit_index"].notna().sum())
    covered = int(merged["climate_available"].sum())
    return merged.drop(columns=["_unit_index"]), {
        "units": len(units),
        "total": total,
        "matched": hit,
        "match_rate": round(hit / total, 3) if total else 0.0,
        "by_method": {"geojson": hit, "unmatched": total - hit},
        "covered": covered,
        "rows": total,
        "rate": round(covered / total, 3) if total else 0.0,
        "years": years,
    }
