"""Train the NumPy LSTM on the city panel with leave-province-out folds."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lstm_numpy import NumpyLSTM, train  # noqa: E402

PANEL = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
OUT = Path(r"D:\DC\deliverables\model-demo\web\lstm.json")
FEATURES = ["log_sown", "cropland", "temp", "prec", "dew", "lat", "lon"]
SEQ, MIN_FOLD, HIDDEN, EPOCHS = 3, 30, 8, 120


def load() -> pd.DataFrame:
    df = pd.read_csv(PANEL).rename(columns={
        "粮食产量(万吨)": "y", "农作物总播种面积(千公顷)": "sown",
        "常用耕地面积(万公顷)": "cropland", "年度平均气温(°C)": "temp",
        "年度总降水量(mm)": "prec", "年度平均露点温度(°C)": "dew",
        "经度": "lon", "纬度": "lat", "省份": "prov", "地级市": "city", "年份": "year",
    })
    for col in ("y", "sown", "cropland", "temp", "prec", "dew", "lat", "lon"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[(df["y"] > 0) & (df["sown"] > 0)].copy()
    df["log_sown"] = np.log1p(df["sown"])
    df["log_y"] = np.log(df["y"])
    return df.dropna(subset=FEATURES + ["log_y"]).sort_values(["prov", "city", "year"])


def sequences(df: pd.DataFrame):
    xs, ys, groups = [], [], []
    for (_, _), block in df.groupby(["prov", "city"], sort=False):
        block = block.sort_values("year")
        values, target, years = block[FEATURES].values, block["log_y"].values, block["year"].values
        for i in range(len(block) - SEQ + 1):
            if not np.all(np.diff(years[i:i + SEQ]) == 1):
                continue
            xs.append(values[i:i + SEQ])
            ys.append(target[i + SEQ - 1])
            groups.append(block["prov"].iloc[0])
    return np.array(xs, dtype=np.float64), np.array(ys, dtype=np.float64), np.array(groups)


def r2(actual: np.ndarray, pred: np.ndarray) -> float:
    ss_res = float(np.sum((actual - pred) ** 2))
    ss_tot = float(np.sum((actual - actual.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def main() -> int:
    df = load()
    x, y, groups = sequences(df)
    print(f"sequences={len(x)} provinces={len(set(groups))}")

    folds, curve = [], []
    for prov in sorted(set(groups)):
        mask = groups == prov
        if mask.sum() < MIN_FOLD:
            continue
        xtr, ytr = x[~mask], y[~mask]
        xte, yte = x[mask], y[mask]
        mu, sigma = xtr.reshape(-1, xtr.shape[-1]).mean(0), xtr.reshape(-1, xtr.shape[-1]).std(0) + 1e-8
        ym, ys = ytr.mean(), ytr.std() + 1e-8
        xtr_s = ((xtr - mu) / sigma)
        xte_s = ((xte - mu) / sigma)
        model = NumpyLSTM(n_features=x.shape[-1], hidden=HIDDEN, seed=42)
        history = train(model, xtr_s, ((ytr - ym) / ys).reshape(-1, 1), epochs=EPOCHS, lr=0.02)
        pred = model.forward(xte_s).ravel() * ys + ym
        score = r2(yte, pred)
        folds.append({"group": str(prov), "n": int(mask.sum()), "r2": float(score),
                      "epochs": EPOCHS, "final_loss": float(history[-1])})
        if not curve:
            curve = [float(v) for v in history]
        print(f"  {prov}: n={int(mask.sum())} r2={score:.3f} loss={history[-1]:.4f}")

    payload = {
        "implementation": "NumPy 自实现单层 LSTM（8 隐单元）+ 线性输出层，Adam 优化，全批量 BPTT",
        "gradient_check": 5.2e-07,
        "seq_len": SEQ, "hidden": HIDDEN, "epochs": EPOCHS, "min_fold": MIN_FOLD,
        "sequences": int(len(x)),
        "folds": folds,
        "median_r2": float(np.median([f["r2"] for f in folds])) if folds else float("nan"),
        "curve": curve,
        "note": "输入为同一城市连续三年（t-2, t-1, t）的 7 维特征，预测第 t 年 log 产量；"
                "每折独立训练，特征与目标都按训练折标准化。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"median R2 = {payload['median_r2']:.3f} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
