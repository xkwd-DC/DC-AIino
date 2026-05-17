"""Y 去趋势（任务 1.6 Butterworth 滤波）—— 接手自王天硕。

输入：
  data/raw/paper_panel/wang_tianshuo_original/分省年度粮食产量数据.xlsx
  data/raw/paper_panel/wang_tianshuo_original/分省播种面积年度数据 (1).xlsx
  data/interim/paper_panel_v2.parquet

输出：
  data/interim/paper_panel_v3.parquet      v2 + 多个 Y 列
  data/interim/yield_detrend_report.md      去趋势效果对照

诊断结论（v1/v2 已确认）：
  Wang 给的"粮食单产风险Y"列从 2011 单调降到 2023，跌 57% — 没真做 Butterworth。

本脚本算法：
  1. 单产 = 粮食产量（万吨）× 10 / 播种面积（千公顷）→ kg/公顷
  2. 每省独立做 3 种去趋势：
     - linear: 减去 OLS 线性趋势（最稳，13 样本足够）
     - butter:  Butterworth low-pass + filtfilt → trend，残差 = 单产 - trend（论文方法）
     - zscore: 每省独立 (y - mean) / std（最简单，类似一阶差分的归一化）
  3. 输出残差作为新 Y 列，所有列都保留

CLI:
    python scripts/data/08_detrend_y.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WANG_FOLDER = PROJECT_ROOT / "data" / "raw" / "paper_panel" / "wang_tianshuo_original"
YIELD_XLSX = WANG_FOLDER / "分省年度粮食产量数据.xlsx"
AREA_XLSX = WANG_FOLDER / "分省播种面积年度数据 (1).xlsx"
V2_PARQUET = PROJECT_ROOT / "data" / "interim" / "paper_panel_v2.parquet"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "paper_panel_v3.parquet"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "interim" / "yield_detrend_report.md"

# 王的 xlsx 用短名（"北京市"=全称版），需要映射到 6 位代码
PROVINCE_MAP: dict[str, str] = {
    "北京市": "110000", "天津市": "120000", "河北省": "130000", "山西省": "140000",
    "内蒙古自治区": "150000", "辽宁省": "210000", "吉林省": "220000", "黑龙江省": "230000",
    "上海市": "310000", "江苏省": "320000", "浙江省": "330000", "安徽省": "340000",
    "福建省": "350000", "江西省": "360000", "山东省": "370000", "河南省": "410000",
    "湖北省": "420000", "湖南省": "430000", "广东省": "440000", "广西壮族自治区": "450000",
    "海南省": "460000", "重庆市": "500000", "四川省": "510000", "贵州省": "520000",
    "云南省": "530000", "西藏自治区": "540000", "陕西省": "610000", "甘肃省": "620000",
    "青海省": "630000", "宁夏回族自治区": "640000", "新疆维吾尔自治区": "650000",
}


def load_wang_wide(path: Path, sheet: str = "Sheet1") -> pd.DataFrame:
    """读王的宽表 (地区 + 各年列) → 长格式 (province_code, year, value)。"""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    # 找 header 行
    header_row = None
    for i in range(min(8, len(raw))):
        if "地区" in str(raw.iloc[i, 0]):
            header_row = i
            break
    if header_row is None:
        raise RuntimeError(f"找不到 header 行（'地区'）于 {path.name}")

    df = raw.iloc[header_row + 1:].copy()
    df.columns = raw.iloc[header_row].tolist()
    df = df.rename(columns={"地区": "province"})
    df = df[df["province"].isin(PROVINCE_MAP)].reset_index(drop=True)

    year_cols = [c for c in df.columns if isinstance(c, str) and c.endswith("年") and 2011 <= int(c[:-1]) <= 2023]
    long = df[["province"] + year_cols].melt(id_vars="province", var_name="year", value_name="value")
    long["year"] = long["year"].str.rstrip("年").astype(int)
    long["province_code"] = long["province"].map(PROVINCE_MAP)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    return long[["province_code", "province", "year", "value"]].sort_values(["province_code", "year"])


def compute_yield(prod: pd.DataFrame, area: pd.DataFrame) -> pd.DataFrame:
    """单产 = 产量(万吨) × 10 / 播种面积(千公顷) → kg/公顷"""
    merged = prod.rename(columns={"value": "production_wan_ton"}).merge(
        area.rename(columns={"value": "sown_qian_ha"})[["province_code", "year", "sown_qian_ha"]],
        on=["province_code", "year"], how="inner",
    )
    merged["yield_kg_per_ha"] = merged["production_wan_ton"] * 10000 / merged["sown_qian_ha"] / 1000 * 1000
    # 万吨 × 10000 = 千克 ; 千公顷 × 1000 = 公顷 ; → kg/公顷
    # 简化：万吨/千公顷 × 10 = kg/公顷
    merged["yield_kg_per_ha"] = merged["production_wan_ton"] * 10000 / (merged["sown_qian_ha"])
    # 万吨/千公顷 单位：1 万吨 = 10000 吨 = 10^7 kg；1 千公顷 = 10^3 ha
    # → kg/ha = (万吨 × 10^7) / (千公顷 × 10^3) = 万吨/千公顷 × 10^4
    merged["yield_kg_per_ha"] = merged["production_wan_ton"] * 1e4 / merged["sown_qian_ha"]
    return merged[["province_code", "province", "year", "production_wan_ton", "sown_qian_ha", "yield_kg_per_ha"]]


def detrend_linear(group: pd.DataFrame) -> pd.Series:
    """每省独立做 OLS 线性去趋势，返回残差。"""
    x = group["year"].values.astype(float)
    y = group["yield_kg_per_ha"].values.astype(float)
    coef = np.polyfit(x, y, 1)
    trend = np.polyval(coef, x)
    return pd.Series(y - trend, index=group.index)


def detrend_butter(group: pd.DataFrame, order: int = 2, fc_normalized: float = 0.25) -> pd.Series:
    """Butterworth low-pass + filtfilt → trend，残差 = y - trend。

    13 样本上 Butterworth 边缘 padding 会有些扭曲，但 filtfilt 比单向 filter 更稳。
    fc_normalized = 0.25 表示 cut-off = 4 年（保留长期趋势，过滤短期波动）。
    """
    y = group["yield_kg_per_ha"].values.astype(float)
    b, a = signal.butter(order, fc_normalized, btype="lowpass")
    pad = min(3 * max(len(a), len(b)), len(y) - 1)
    trend = signal.filtfilt(b, a, y, padlen=pad if pad > 0 else None)
    return pd.Series(y - trend, index=group.index)


def detrend_zscore(group: pd.DataFrame) -> pd.Series:
    """每省独立 (y - mean) / std。"""
    y = group["yield_kg_per_ha"].values.astype(float)
    mu, sd = y.mean(), y.std()
    return pd.Series((y - mu) / sd if sd > 0 else 0, index=group.index)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Y 去趋势 (task 1.6) → paper_panel_v3.parquet")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--butter-fc", type=float, default=0.25, help="Butterworth 归一化截止频率")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    prod = load_wang_wide(YIELD_XLSX)
    area = load_wang_wide(AREA_XLSX)
    yld = compute_yield(prod, area)
    logging.info("单产计算完成：%d 行（期望 31×13=403）", len(yld))

    yld = yld.sort_values(["province_code", "year"]).reset_index(drop=True)

    yld["y_linear"] = yld.groupby("province_code", group_keys=False).apply(detrend_linear)
    yld["y_butter"] = yld.groupby("province_code", group_keys=False).apply(detrend_butter, order=2, fc_normalized=args.butter_fc)
    yld["y_zscore"] = yld.groupby("province_code", group_keys=False).apply(detrend_zscore)

    # Merge to v2 panel
    v2 = pd.read_parquet(V2_PARQUET)
    v3 = v2.merge(
        yld[["province_code", "year", "production_wan_ton", "sown_qian_ha",
             "yield_kg_per_ha", "y_linear", "y_butter", "y_zscore"]],
        on=["province_code", "year"], how="left",
    )
    v3 = v3.rename(columns={"y": "y_wang_original"})  # 王原版改名，避免歧义

    args.out.parent.mkdir(parents=True, exist_ok=True)
    v3.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s（%d 行 × %d 列）", args.out, len(v3), len(v3.columns))

    # === 报告：去趋势效果 ===
    print()
    print("=== 各 Y 列时间漂移诊断（年均值，应近常数）===")
    print(f"{'year':6s}{'wang_orig':>12s}{'yield_raw':>12s}{'y_linear':>12s}{'y_butter':>12s}{'y_zscore':>12s}")
    by_year = v3.groupby("year")[["y_wang_original", "yield_kg_per_ha", "y_linear", "y_butter", "y_zscore"]].mean()
    for yr, row in by_year.iterrows():
        print(f"{yr!s:6s}{row['y_wang_original']:12.4f}{row['yield_kg_per_ha']:12.1f}{row['y_linear']:12.1f}{row['y_butter']:12.1f}{row['y_zscore']:12.4f}")

    # 残差应该 mean≈0 且时间序列无趋势；用 OLS 斜率检验
    print()
    print("=== 平稳性诊断（残差应 mean≈0，slope≈0）===")
    import numpy as np
    years = by_year.index.values.astype(float)
    for col in ["y_wang_original", "yield_kg_per_ha", "y_linear", "y_butter", "y_zscore"]:
        vals = by_year[col].values
        m = vals.mean()
        s = vals.std()
        slope, _ = np.polyfit(years, vals, 1)
        slope_per_decade = slope * 10
        # 判定：残差 mean 离零远（>1%级别 of original std）或 slope 显著
        is_residual = col in ("y_linear", "y_butter", "y_zscore")
        if is_residual:
            mean_ok = abs(m) < 0.05 * abs(by_year["yield_kg_per_ha"].std())
            slope_ok = abs(slope_per_decade) < 0.02 * abs(by_year["yield_kg_per_ha"].std())
            status = "✓ 平稳" if mean_ok and slope_ok else "❌ 仍有漂移"
        else:
            status = ""
        print(f"  {col:20s} mean={m:9.2f}  std={s:8.2f}  slope/decade={slope_per_decade:+8.2f}  {status}")

    # 报告
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        f"""# Y 去趋势报告（任务 1.6）

**接手**：原王天硕，2026-05-17 起石灵子。
**输入**：王的"分省年度粮食产量数据.xlsx" + "分省播种面积年度数据 (1).xlsx"
**输出**：data/interim/paper_panel_v3.parquet

## 单产计算

单产 (kg/公顷) = 粮食产量 (万吨) × 10000 / 播种面积 (千公顷)

行数：{len(yld)}（期望 31 × 13 = 403）

## 三种去趋势方法

| 方法 | 列名 | 适用 |
|---|---|---|
| 线性 (OLS) | `y_linear` | **推荐主用**：13 样本足够稳定，结果好解释 |
| Butterworth | `y_butter` | 论文原方法（filtfilt, order=2, fc={args.butter_fc}） |
| Z-score | `y_zscore` | 最简单，作 sanity baseline |

## 时间漂移诊断

各 Y 列 2011 → 2023 年均值跌幅：

```
{by_year.round(2).to_string()}
```

## 给熊鑫的使用建议

```python
import pandas as pd
df = pd.read_parquet("data/interim/paper_panel_v3.parquet")

# 推荐：用 y_linear 作训练目标
X = df[["irr","flood","sun","temp","spei","prec","mech","fert","drou_a","flood_a","ndvi"]]
y = df["y_linear"]   # 残差，已去除长期趋势

# 对比验证：跑论文原方法 y_butter，看 R² 是否一致
y_butter = df["y_butter"]
```

如果时间漂移仍有问题（跌幅 > 30%），调 `--butter-fc` 参数或换更长历史序列重做。

## 保留列

- `y_wang_original`：王原版（漂移 57%，作 reference 不用于训练）
- `yield_kg_per_ha`：原始单产，可用于自定义去趋势
""",
        encoding="utf-8",
    )
    logging.info("报告写入 %s", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
