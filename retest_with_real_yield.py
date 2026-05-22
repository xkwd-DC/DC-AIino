"""重新测：X 特征对石灵子重算的 Y（基于真实单产）的预测力。

之前结论"R²≈0"是在王天硕坏 Y 上做的 Butterworth，输入就错。
现在用石灵子 v3 的 3 个新 Y 重测——这才是公允评估。
"""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

BASE_10 = ["irr", "flood", "sun", "temp", "spei", "prec", "mech", "fert", "drou_a", "flood_a"]
BASE_11 = BASE_10 + ["ndvi"]
HYPER = dict(learning_rate=0.1, max_depth=6, n_estimators=150, objective="reg:squarederror")
SEEDS = list(range(10))

df = pd.read_parquet("data/interim/paper_panel_v3.parquet")
print(f"v3 shape: {df.shape}    rows: {len(df)}\n")

# 各 Y 的基本统计
print("各 Y 列统计：")
for c in ["y_wang_original", "yield_kg_per_ha", "y_linear", "y_butter", "y_zscore"]:
    if c in df.columns:
        print(f"  {c:20s} mean={df[c].mean():>10.3f}  std={df[c].std():>10.3f}")
print()


def run(target: str, cols: list[str]) -> dict:
    X = df[cols].values
    y = df[target].values
    tr_r2s, te_r2s, te_rmses = [], [], []
    for seed in SEEDS:
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=seed)
        sc = StandardScaler()
        X_tr = sc.fit_transform(X_tr); X_te = sc.transform(X_te)
        m = xgb.XGBRegressor(random_state=seed, **HYPER)
        m.fit(X_tr, y_tr)
        tr_r2s.append(r2_score(y_tr, m.predict(X_tr)))
        te_r2s.append(r2_score(y_te, m.predict(X_te)))
        te_rmses.append(root_mean_squared_error(y_te, m.predict(X_te)))
    return dict(
        tr_r2=np.mean(tr_r2s),
        te_r2_mean=np.mean(te_r2s), te_r2_std=np.std(te_r2s),
        te_rmse=np.mean(te_rmses),
    )


print("=" * 92)
print("石灵子 v3 各 Y 列的 XGBoost 预测力（10 种子均值）")
print("=" * 92)
print(f"{'Y 列':<22s}{'特征':<10s}{'tr R²':>10s}{'te R² mean':>13s}{'te R² std':>12s}{'te RMSE':>14s}")
print("-" * 92)

TARGETS = [
    ("y_wang_original", "王天硕原版"),
    ("yield_kg_per_ha", "真实单产"),
    ("y_linear", "线性残差"),
    ("y_butter", "Butterworth 残差"),
    ("y_zscore", "Z-score 残差"),
]

for target, _ in TARGETS:
    for cols_name, cols in [("10维", BASE_10), ("11维+NDVI", BASE_11)]:
        m = run(target, cols)
        print(f"{target:<22s}{cols_name:<10s}{m['tr_r2']:>10.4f}"
              f"{m['te_r2_mean']:>13.4f}{m['te_r2_std']:>12.4f}{m['te_rmse']:>14.4f}")
    print("-" * 92)
