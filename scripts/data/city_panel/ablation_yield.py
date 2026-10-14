"""Ablation: drop the scale variables and model yield per sown area instead.

Answers whether the climate features carry signal on their own, or whether the
high R² of the level model comes from cropland/sown-area scale.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_squared_error, r2_score

warnings.filterwarnings("ignore")

PANEL = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
OUT = Path(r"D:\DC\_scan\ablation.txt")

CLIMATE_FEATURES = ["temp", "prec", "dew", "lat", "lon"]
ALL_FEATURES = ["log_sown", "cropland"] + CLIMATE_FEATURES
PARAMS = dict(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8,
              colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0, random_state=42, n_jobs=-1)


def load() -> pd.DataFrame:
    df = pd.read_csv(PANEL).rename(columns={
        "粮食产量(万吨)": "yield_wan", "农作物总播种面积(千公顷)": "sown",
        "常用耕地面积(万公顷)": "cropland", "年度平均气温(°C)": "temp",
        "年度总降水量(mm)": "prec", "年度平均露点温度(°C)": "dew", "产量数据来源": "source",
        "经度": "lon", "纬度": "lat",
    })
    df = df[(df["yield_wan"] > 0) & (df["sown"] > 0)].copy()
    df["log_sown"] = np.log1p(df["sown"])
    df["log_yield"] = np.log(df["yield_wan"])
    df["log_yield_per_area"] = df["log_yield"] - df["log_sown"]
    for col in ("cropland", "temp", "prec", "dew"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=ALL_FEATURES + ["log_yield", "log_yield_per_area"])


def lpo(df: pd.DataFrame, target: str, features: list[str]) -> tuple[float, float, int]:
    scores = []
    for prov in sorted(df["省份"].unique()):
        test = df[df["省份"] == prov]
        train = df[df["省份"] != prov]
        model = xgb.XGBRegressor(**PARAMS)
        model.fit(train[features], train[target])
        scores.append(r2_score(test[target], model.predict(test[features])))
    arr = np.array(scores)
    return float(np.median(arr)), float(arr.mean()), int((arr > 0).sum())


def main() -> int:
    df = load()
    lines = []
    for label, subset in (("全部样本", df), ("仅官方值", df[df["source"] != "县级加总校准估算"])):
        lines.append(f"== {label}（{len(subset)} 行）")
        med, mean, pos = lpo(subset, "log_yield", ALL_FEATURES)
        lines.append(f"  水平模型 log(产量)，含规模变量：中位 R² {med:.4f}，均值 {mean:.4f}，正折 {pos}/13")
        med, mean, pos = lpo(subset, "log_yield", CLIMATE_FEATURES)
        lines.append(f"  水平模型 log(产量)，仅气候变量：中位 R² {med:.4f}，均值 {mean:.4f}，正折 {pos}/13")
        med, mean, pos = lpo(subset, "log_yield_per_area", CLIMATE_FEATURES)
        lines.append(f"  单产模型 log(产量/播种面积)，仅气候变量：中位 R² {med:.4f}，均值 {mean:.4f}，正折 {pos}/13")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
