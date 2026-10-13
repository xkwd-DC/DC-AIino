"""Re-run the city-level XGBoost model on the new prefecture panel.

Protocol follows the project's existing v5/v6 setup:
  target  log(粮食产量)   features 规模控制 + 气候 + 空间
  CV      留一省 / 留一年 / 随机 8:2（10 种子）/ 时间外推（<=2019 → 2020-2024）
Run twice: all rows, and official-only rows (the estimated rows are derived from
county aggregates that also feed the features, so they are checked separately).
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
OUT = Path(r"D:\DC\deliverables\city-grain-data\模型复跑结果.md")

FEATURES = ["log_sown", "cropland", "temp", "prec", "dew", "lat", "lon"]
XGB_PARAMS = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
}


def load() -> pd.DataFrame:
    df = pd.read_csv(PANEL)
    df = df.rename(columns={
        "粮食产量(万吨)": "yield_wan",
        "农作物总播种面积(千公顷)": "sown",
        "常用耕地面积(万公顷)": "cropland",
        "年度平均气温(°C)": "temp",
        "年度总降水量(mm)": "prec",
        "年度平均露点温度(°C)": "dew",
        "经度": "lon",
        "纬度": "lat",
        "产量数据来源": "source",
    })
    df["sown"] = pd.to_numeric(df["sown"], errors="coerce")
    df = df[(df["yield_wan"] > 0) & (df["sown"] > 0)].copy()
    df["log_yield"] = np.log(df["yield_wan"])
    df["log_sown"] = np.log1p(df["sown"].fillna(0))
    for col in ("cropland", "temp", "prec", "dew"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=FEATURES + ["log_yield"])
    return df


def evaluate(train: pd.DataFrame, test: pd.DataFrame) -> tuple[float, float, np.ndarray]:
    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(train[FEATURES], train["log_yield"])
    pred = model.predict(test[FEATURES])
    return (
        r2_score(test["log_yield"], pred),
        float(np.sqrt(mean_squared_error(test["log_yield"], pred))),
        model.feature_importances_,
    )


def leave_one_group(df: pd.DataFrame, group: str) -> list[dict]:
    folds = []
    for value in sorted(df[group].unique()):
        test = df[df[group] == value]
        train = df[df[group] != value]
        if len(test) < 10 or len(train) < 50:
            continue
        r2, rmse, _ = evaluate(train, test)
        folds.append({"group": value, "n_test": len(test), "r2": r2, "rmse": rmse})
    return folds


def random_split(df: pd.DataFrame, seeds: int = 10) -> dict:
    scores = []
    for seed in range(seeds):
        shuffled = df.sample(frac=1.0, random_state=seed)
        cut = int(len(shuffled) * 0.8)
        train, test = shuffled.iloc[:cut], shuffled.iloc[cut:]
        r2, rmse, _ = evaluate(train, test)
        scores.append((r2, rmse))
    arr = np.array(scores)
    return {"r2_mean": arr[:, 0].mean(), "r2_std": arr[:, 0].std(), "rmse_mean": arr[:, 1].mean()}


def time_extrapolation(df: pd.DataFrame, cut_year: int = 2019) -> dict:
    train = df[df["年份"] <= cut_year]
    test = df[df["年份"] > cut_year]
    if len(test) < 10:
        return {}
    r2, rmse, _ = evaluate(train, test)
    return {"r2": r2, "rmse": rmse, "n_test": len(test)}


def summarise(name: str, folds: list[dict], lines: list[str]) -> None:
    if not folds:
        lines.append(f"### {name}\n\n样本不足，跳过。\n")
        return
    r2s = sorted(f["r2"] for f in folds)
    pool = np.median(r2s)
    positive = sum(1 for r in r2s if r > 0)
    lines.append(f"### {name}\n")
    lines.append(f"- 折数 {len(folds)}，中位 R² = **{pool:.4f}**，均值 {np.mean(r2s):.4f}，"
                 f"最小 {r2s[0]:.4f}，最大 {r2s[-1]:.4f}，R²>0 的折 {positive}/{len(folds)}")
    lines.append("")
    lines.append("| 折 | 测试样本 | R² | RMSE |")
    lines.append("|---|---|---|---|")
    for f in folds:
        lines.append(f"| {f['group']} | {f['n_test']} | {f['r2']:.4f} | {f['rmse']:.4f} |")
    lines.append("")


def main() -> int:
    df = load()
    lines = ["# 用新市级面板复跑 XGBoost 模型", ""]
    lines.append(f"- 样本：{len(df)} 行，{df['省份'].nunique()} 省，{df['地级市'].nunique()} 市，"
                 f"年份 {int(df['年份'].min())}–{int(df['年份'].max())}")
    lines.append(f"- 目标：log(粮食产量)，单位万吨")
    lines.append(f"- 特征（{len(FEATURES)}）：" + "、".join(FEATURES))
    lines.append("- 超参：n_estimators=300, max_depth=5, lr=0.05, subsample=0.8, colsample=0.8")
    lines.append("")

    for label, subset in (
        ("全部样本", df),
        ("仅官方值样本", df[df["source"] != "县级加总校准估算"]),
    ):
        lines.append(f"## {label}（{len(subset)} 行）")
        lines.append("")
        folds = leave_one_group(subset, "省份")
        summarise("留一省交叉验证（空间外推）", folds, lines)
        folds = leave_one_group(subset, "年份")
        summarise("留一年交叉验证（时序外推）", folds, lines)
        rs = random_split(subset)
        lines.append(f"### 随机 8:2（10 组种子）\n")
        lines.append(f"- R² = **{rs['r2_mean']:.4f} ± {rs['r2_std']:.4f}**，RMSE = {rs['rmse_mean']:.4f}")
        lines.append("")
        te = time_extrapolation(subset)
        if te:
            lines.append(f"### 时间外推（≤2019 训练 → 2020–2024 测试）\n")
            lines.append(f"- R² = **{te['r2']:.4f}**，RMSE = {te['rmse']:.4f}，测试样本 {te['n_test']}")
            lines.append("")

    # 全样本训练后的特征重要性
    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(df[FEATURES], df["log_yield"])
    lines.append("## 特征重要性（全样本训练）\n")
    lines.append("| 特征 | 重要性 |")
    lines.append("|---|---|")
    for feat, imp in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
        lines.append(f"| {feat} | {imp:.4f} |")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:40]))
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
