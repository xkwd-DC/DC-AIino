"""对照三版数据 × XGBoost 基线（10 种子均值）。

回答两个问题：
  1. 石灵子 v2（修了 prec/sun）能把 XGB R² 从 raw 的 0.50 拉高多少？
  2. 加入 NDVI（11 维）相对 10 维提升多少？

不保存任何交付物，只打印对照表。
"""
from pathlib import Path
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

BASE_10 = ["irr", "flood", "sun", "temp", "spei", "prec", "mech", "fert", "drou_a", "flood_a"]
NDVI_COL = "ndvi"  # 生长季 4-10 月均值版（doc 08 §3.2 默认列）

HYPER = dict(learning_rate=0.1, max_depth=6, n_estimators=150,
             objective="reg:squarederror")
SEEDS = list(range(10))

CONFIGS = [
    ("raw 10 维", "data/interim/paper_panel_raw.parquet", BASE_10),
    ("v2  10 维", "data/interim/paper_panel_v2.parquet",  BASE_10),
    ("v1  11 维 (+NDVI)", "data/interim/paper_panel_v1.parquet", BASE_10 + [NDVI_COL]),
    ("v2  11 维 (+NDVI)", "data/interim/paper_panel_v2.parquet", BASE_10 + [NDVI_COL]),
]


def run_one(path: str, cols: list[str], seed: int) -> tuple[float, float, float, float]:
    df = pd.read_parquet(path)
    X = df[cols].values
    y = df["y"].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=seed)
    sc = StandardScaler()
    X_tr = sc.fit_transform(X_tr)
    X_te = sc.transform(X_te)
    model = xgb.XGBRegressor(random_state=seed, **HYPER)
    model.fit(X_tr, y_tr)
    p_tr = model.predict(X_tr)
    p_te = model.predict(X_te)
    return (
        r2_score(y_tr, p_tr),
        r2_score(y_te, p_te),
        root_mean_squared_error(y_tr, p_tr),
        root_mean_squared_error(y_te, p_te),
    )


print("=" * 88)
print("数据版本对照 — XGBoost 基线（10 种子均值，论文超参）")
print("=" * 88)
print(f"{'配置':<22s}{'te_R² mean':>13s}{'te_R² std':>12s}"
      f"{'te_RMSE mean':>15s}{'tr_R² mean':>13s}{'判断':>14s}")
print("-" * 88)

for name, path, cols in CONFIGS:
    if not Path(path).exists():
        print(f"{name:<22s}  数据缺失：{path}")
        continue
    results = [run_one(path, cols, s) for s in SEEDS]
    tr_r2 = np.array([r[0] for r in results])
    te_r2 = np.array([r[1] for r in results])
    te_rmse = np.array([r[3] for r in results])
    judge = "✅ ≥0.62" if te_r2.mean() >= 0.62 else f"{te_r2.mean() - 0.62:+.3f}"
    print(f"{name:<22s}{te_r2.mean():>13.4f}{te_r2.std():>12.4f}"
          f"{te_rmse.mean():>15.4f}{tr_r2.mean():>13.4f}{judge:>14s}")

print("-" * 88)
print("参照：论文 R²=0.6293（XGB，10 维）/ 0.6619（LSTM，11 维）")
print()
print("注意：Y 尚未做 Butterworth 去趋势（1.6 task），任何版本的 R² 上限都受此压制。")
