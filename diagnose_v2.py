"""第二轮诊断：找出真正的过拟合根因

1. Y 按年的分布 → 看 Y 是否真有时间漂移
2. 多种子下基线稳定性 → 看 random_state=42 是不是运气差
3. 小模型对比 → 看降低模型容量能否压住过拟合
"""
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

DATA = Path("data/interim/paper_panel_raw.parquet")
FEATURES = ["irr", "flood", "sun", "temp", "spei", "prec",
            "mech", "fert", "drou_a", "flood_a"]
df = pd.read_parquet(DATA)
X = df[FEATURES].values
y = df["y"].values

# ─── 诊断 1：Y 按年的分布 ───────────────────────────────────────────────
print("=" * 76)
print("诊断 1：Y 按年的分布（若 2021-2023 显著偏离，说明数据有时间漂移）")
print("=" * 76)
yearly = df.groupby("year")["y"].agg(["count", "mean", "std", "min", "max"]).round(4)
print(yearly.to_string())
print()
mean_2011_2020 = df[df["year"] <= 2020]["y"].mean()
mean_2021_2023 = df[df["year"] >= 2021]["y"].mean()
print(f"2011-2020 Y 均值：{mean_2011_2020:.4f}")
print(f"2021-2023 Y 均值：{mean_2021_2023:.4f}")
print(f"差异：{abs(mean_2021_2023 - mean_2011_2020):.4f}（绝对值），"
      f"{(mean_2021_2023/mean_2011_2020 - 1)*100:+.1f}%（相对）")

# ─── 诊断 2：多种子下随机 8:2 的稳定性 ──────────────────────────────────
print()
print("=" * 76)
print("诊断 2：多种子下，基线 vs 小模型 的稳定性")
print("=" * 76)


def evaluate(seed, hyper):
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=seed)
    s = StandardScaler()
    X_tr_s = s.fit_transform(X_tr)
    X_te_s = s.transform(X_te)
    m = xgb.XGBRegressor(**hyper)
    m.fit(X_tr_s, y_tr)
    return (
        r2_score(y_tr, m.predict(X_tr_s)),
        r2_score(y_te, m.predict(X_te_s)),
        root_mean_squared_error(y_te, m.predict(X_te_s)),
    )


BASE  = dict(learning_rate=0.1, max_depth=6, n_estimators=150,
             objective="reg:squarederror", random_state=42)
SMALL = dict(learning_rate=0.05, max_depth=3, n_estimators=200, reg_lambda=10,
             objective="reg:squarederror", random_state=42)

print(f"{'seed':<6s}"
      f"{'BASE 训练R²':>12s}{'BASE 测试R²':>12s}{'BASE RMSE':>12s}"
      f"{'SMALL 训练R²':>14s}{'SMALL 测试R²':>14s}{'SMALL RMSE':>12s}")
print("-" * 84)

records_base, records_small = [], []
for seed in range(10):
    btr, bte, brmse = evaluate(seed, BASE)
    str_, ste, srmse = evaluate(seed, SMALL)
    records_base.append((btr, bte, brmse))
    records_small.append((str_, ste, srmse))
    print(f"{seed:<6d}{btr:>12.4f}{bte:>12.4f}{brmse:>12.4f}"
          f"{str_:>14.4f}{ste:>14.4f}{srmse:>12.4f}")

print()
print("─── 10 种子平均 ───")
base_avg = np.array(records_base).mean(axis=0)
small_avg = np.array(records_small).mean(axis=0)
print(f"BASE  平均  训练R²={base_avg[0]:.4f}  测试R²={base_avg[1]:.4f}  RMSE={base_avg[2]:.4f}")
print(f"SMALL 平均  训练R²={small_avg[0]:.4f}  测试R²={small_avg[1]:.4f}  RMSE={small_avg[2]:.4f}")
print()
print("论文期望：测试 R² = 0.6293, RMSE = 0.0051")
print("doc 07 硬指标：测试 R² ≥ 0.62, RMSE ≤ 0.0055")
