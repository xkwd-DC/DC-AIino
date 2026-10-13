"""Robustness: same protocol without the cropland feature (larger sample)."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score

warnings.filterwarnings("ignore")

PANEL = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
OUT = Path(r"D:\DC\_scan\robust.txt")
PARAMS = dict(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8,
              colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0, random_state=42, n_jobs=-1)


def load() -> pd.DataFrame:
    df = pd.read_csv(PANEL).rename(columns={
        "粮食产量(万吨)": "y", "农作物总播种面积(千公顷)": "sown",
        "年度平均气温(°C)": "temp", "年度总降水量(mm)": "prec",
        "年度平均露点温度(°C)": "dew", "产量数据来源": "source",
        "经度": "lon", "纬度": "lat",
    })
    df = df[(df["y"] > 0) & (df["sown"] > 0)].copy()
    df["log_sown"] = np.log1p(df["sown"])
    df["log_y"] = np.log(df["y"])
    for c in ("temp", "prec", "dew"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["log_sown", "temp", "prec", "dew", "lat", "lon", "log_y"])


def lpo(df: pd.DataFrame, features: list[str]) -> tuple[float, float, int, int]:
    scores = []
    for prov in sorted(df["省份"].unique()):
        test, train = df[df["省份"] == prov], df[df["省份"] != prov]
        model = xgb.XGBRegressor(**PARAMS)
        model.fit(train[features], train["log_y"])
        scores.append(r2_score(test["log_y"], model.predict(test[features])))
    arr = np.array(scores)
    return float(np.median(arr)), float(arr.mean()), int((arr > 0).sum()), len(df)


def main() -> int:
    df = load()
    lines = []
    for label, sub in (("全部样本", df), ("仅官方值", df[df["source"] != "县级加总校准估算"])):
        for feats in (["log_sown", "temp", "prec", "dew", "lat", "lon"],
                      ["log_sown"], ["log_sown", "temp"]):
            med, mean, pos, n = lpo(sub, feats)
            lines.append(f"{label} | 特征 {'+'.join(feats)} | n={n} | 中位 R² {med:.4f} | 均值 {mean:.4f} | 正折 {pos}/13")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
