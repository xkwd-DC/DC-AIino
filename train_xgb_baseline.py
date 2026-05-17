"""XGBoost 基线（v3 真实单产，11 维含 NDVI）

数据：data/interim/paper_panel_v3.parquet（27 列，N=403）—— 来自石灵子 PR #7 重算
Target：yield_kg_per_ha（真实单产 kg/ha，由原始 .xlsx 重算，非王天硕已煮熟的 Y）
特征：11 维（原论文 10 维 + NDVI）
协议：10 种子 8:2 split，报告 R² mean ± std；SHAP top-5 取 10 种子平均
申报书硬指标：R² ≥ 0.62
  旧 RMSE 阈值 0.0055 不适用（target 单位已从 normalized y → kg/ha）

跑法：/home/xxfql/DC-AIino/.venv/bin/python /home/xxfql/DC-AIino/train_xgb_baseline.py

背景：project_v3_real_yield_finding.md（2026-05-17 v3 反转，路线 E 第 1 项）
"""
from pathlib import Path
import json
import hashlib
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# ─── 路径 / target ─────────────────────────────────────────────────────────
DATA_PATH = Path("data/interim/paper_panel_v3.parquet")
MODELS_DIR = Path("backend/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_COL = "yield_kg_per_ha"

# ─── 特征列（parquet 小写 ↔ 训练大写，与 inference.py 一致）──────────────
# 11 维 = 论文 10 维 + NDVI（v1 入库后扩）
LOWERCASE_TO_TRAINING = {
    "irr": "Irr", "flood": "Flood_R", "sun": "Sun", "temp": "Temp",
    "spei": "SPEI", "prec": "Prec", "mech": "Mech", "fert": "Fert",
    "drou_a": "Drou_A", "flood_a": "Flood_A",
    "ndvi": "NDVI",
}
FEATURE_COLS_LOWER = list(LOWERCASE_TO_TRAINING.keys())
FEATURE_COLS_TRAINING = list(LOWERCASE_TO_TRAINING.values())

# ─── 协议 ────────────────────────────────────────────────────────────────
SEEDS = list(range(10))  # 0..9
HYPER = dict(
    learning_rate=0.1,
    max_depth=6,
    n_estimators=150,
    objective="reg:squarederror",
)
R2_TARGET = 0.62  # 申报书 doc 07 §3.1 硬指标（target-agnostic 的拟合优度阈值）

# ─── 1. 加载数据 ─────────────────────────────────────────────────────────
print("=" * 72)
print(f"1. 加载真实数据 — target = {TARGET_COL}")
print("=" * 72)
df = pd.read_parquet(DATA_PATH)
data_hash = hashlib.md5(DATA_PATH.read_bytes()).hexdigest()[:12]
print(f"数据：{DATA_PATH}（MD5 前 12 位：{data_hash}）")
print(f"规模：{df.shape[0]} 行 × {len(FEATURE_COLS_LOWER)} 维 X + 1 维 y")
print(f"特征：{FEATURE_COLS_LOWER}")
print(
    f"y 统计：mean={df[TARGET_COL].mean():.1f}  std={df[TARGET_COL].std():.1f}  "
    f"范围=[{df[TARGET_COL].min():.0f}, {df[TARGET_COL].max():.0f}] kg/ha"
)

X_raw_full = df[FEATURE_COLS_LOWER].values
y_full = df[TARGET_COL].values

# ─── 2. 10 种子训练 ─────────────────────────────────────────────────────
print()
print("=" * 72)
print(f"2. 10 种子训练（8:2 split, hyper={HYPER}）")
print("=" * 72)

results = []
shap_abs_per_seed = []

for seed in SEEDS:
    X_tr_raw, X_te_raw, y_tr, y_te = train_test_split(
        X_raw_full, y_full, test_size=0.2, random_state=seed
    )
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_tr_raw)
    X_te = scaler.transform(X_te_raw)

    model = xgb.XGBRegressor(random_state=seed, **HYPER)
    model.fit(X_tr, y_tr)

    yp_tr = model.predict(X_tr)
    yp_te = model.predict(X_te)
    tr_r2 = r2_score(y_tr, yp_tr)
    te_r2 = r2_score(y_te, yp_te)
    tr_rmse = root_mean_squared_error(y_tr, yp_tr)
    te_rmse = root_mean_squared_error(y_te, yp_te)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_te)
    shap_abs_per_seed.append(np.abs(shap_values).mean(axis=0))

    results.append(
        dict(
            seed=seed,
            tr_r2=tr_r2,
            te_r2=te_r2,
            tr_rmse_kg_per_ha=tr_rmse,
            te_rmse_kg_per_ha=te_rmse,
        )
    )
    print(
        f"  seed={seed:2d}  tr_R²={tr_r2:.4f}  te_R²={te_r2:.4f}  "
        f"te_RMSE={te_rmse:6.1f} kg/ha"
    )

te_r2s = np.array([r["te_r2"] for r in results])
tr_r2s = np.array([r["tr_r2"] for r in results])
te_rmses = np.array([r["te_rmse_kg_per_ha"] for r in results])
tr_rmses = np.array([r["tr_rmse_kg_per_ha"] for r in results])

# ─── 3. 汇总评估 ────────────────────────────────────────────────────────
print()
print("=" * 72)
print("3. 10 种子汇总")
print("=" * 72)
print(
    f"  test  R²    mean={te_r2s.mean():.4f}  std={te_r2s.std():.4f}  "
    f"[min={te_r2s.min():.4f}, max={te_r2s.max():.4f}]"
)
print(f"  train R²    mean={tr_r2s.mean():.4f}  std={tr_r2s.std():.4f}")
print(f"  test  RMSE  mean={te_rmses.mean():.1f} kg/ha  std={te_rmses.std():.1f}")
print(f"  train RMSE  mean={tr_rmses.mean():.1f} kg/ha  std={tr_rmses.std():.1f}")
print()
passed = te_r2s.mean() >= R2_TARGET
status_str = (
    f"✅ 通过 (mean test R² = {te_r2s.mean():.4f})"
    if passed
    else f"❌ 未达 (mean test R² = {te_r2s.mean():.4f})"
)
print(f"  申报书硬指标 R² ≥ {R2_TARGET}：{status_str}")

# ─── 4. SHAP Top-5（10 种子 mean|SHAP| 平均） ──────────────────────────
print()
print("=" * 72)
print("4. SHAP 特征重要性(10 种子平均 mean|SHAP|)")
print("=" * 72)
shap_mean_across_seeds = np.mean(np.stack(shap_abs_per_seed), axis=0)
ranked = sorted(
    zip(FEATURE_COLS_LOWER, shap_mean_across_seeds), key=lambda x: -x[1]
)
for i, (name, val) in enumerate(ranked[:5], 1):
    bar = "█" * int(val / ranked[0][1] * 30)
    print(f"  {i}. {name:<10s}{val:>12.4f}  {bar}")

top3_actual = [n for n, _ in ranked[:3]]
top3_expected = ["irr", "flood", "sun"]
match = top3_actual == top3_expected
print()
print(f"论文期望 Top 3：irr > flood > sun")
print(f"实测 Top 3：    {' > '.join(top3_actual)}    {'✅ 一致' if match else '⚠️ 不一致'}")

# ─── 5. 保存代表 model（test R² 最贴近中位数的 seed）─────────────────
print()
print("=" * 72)
print("5. 保存代表模型到 backend/models/")
print("=" * 72)
median_r2 = float(np.median(te_r2s))
representative_idx = int(np.argmin(np.abs(te_r2s - median_r2)))
representative_seed = int(results[representative_idx]["seed"])
representative_te_r2 = results[representative_idx]["te_r2"]
print(
    f"  选 seed={representative_seed}（test R²={representative_te_r2:.4f}）"
    f"作代表 —— 最贴近 10 种子中位数 {median_r2:.4f}"
)

# 用代表 seed 重新训练 final 模型 + scaler（覆盖王天硕坏 Y 时代的产物）
X_tr_raw, X_te_raw, y_tr, y_te = train_test_split(
    X_raw_full, y_full, test_size=0.2, random_state=representative_seed
)
final_scaler = StandardScaler()
X_tr = final_scaler.fit_transform(X_tr_raw)
final_model = xgb.XGBRegressor(random_state=representative_seed, **HYPER)
final_model.fit(X_tr, y_tr)

joblib.dump(final_model, MODELS_DIR / "xgb_model.pkl")
joblib.dump(final_scaler, MODELS_DIR / "scaler.pkl")
(MODELS_DIR / "feature_columns.json").write_text(
    json.dumps(FEATURE_COLS_TRAINING, ensure_ascii=False, indent=2)
)

# 10 种子完整结果落盘
seeds_dump = dict(
    target=TARGET_COL,
    data_path=str(DATA_PATH),
    data_md5_12=data_hash,
    n_rows=int(len(df)),
    n_features=len(FEATURE_COLS_LOWER),
    feature_cols_lower=FEATURE_COLS_LOWER,
    feature_cols_training=FEATURE_COLS_TRAINING,
    seeds=SEEDS,
    hyper=HYPER,
    per_seed=results,
    summary=dict(
        test_r2_mean=float(te_r2s.mean()),
        test_r2_std=float(te_r2s.std()),
        test_r2_min=float(te_r2s.min()),
        test_r2_max=float(te_r2s.max()),
        test_rmse_kg_per_ha_mean=float(te_rmses.mean()),
        test_rmse_kg_per_ha_std=float(te_rmses.std()),
        train_r2_mean=float(tr_r2s.mean()),
        train_r2_std=float(tr_r2s.std()),
    ),
    shap_top5=[
        {"feature": n, "mean_abs_shap": float(v)} for n, v in ranked[:5]
    ],
    representative_seed=representative_seed,
    declared_r2_target=R2_TARGET,
    passed=bool(passed),
)
(MODELS_DIR / "xgb_seeds_results.json").write_text(
    json.dumps(seeds_dump, ensure_ascii=False, indent=2)
)

# Model card
shap_lines = "\n".join(
    [f"{i}. {name}: {val:.4f}" for i, (name, val) in enumerate(ranked[:5], 1)]
)
model_card = f"""# Model Card — XGBoost 基线（v3 真实单产，11 维）

## 训练信息
- 训练日期：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- 训练人：熊鑫
- 数据源：{DATA_PATH}（MD5 前 12 位 `{data_hash}`，由石灵子 PR #7 重算）
- 数据规模：N = {len(df)}（31 省 × 13 年），11 维 X（原 10 维 + NDVI）
- Target：`{TARGET_COL}`（真实单产 kg/ha，由原始 .xlsx 重算，**非王天硕已煮熟的 Y**）
- 协议：10 种子 `{SEEDS}`，8:2 split，超参固定

## 超参（论文 §4.1）
```json
{json.dumps(HYPER, indent=2)}
```

## 指标（10 种子）

| 指标 | 训练集 mean | 训练集 std | 测试集 mean | 测试集 std | 申报书硬指标 | 状态 |
|---|---|---|---|---|---|---|
| R² | {tr_r2s.mean():.4f} | {tr_r2s.std():.4f} | {te_r2s.mean():.4f} | {te_r2s.std():.4f} | ≥ 0.62 | {'✅' if passed else '❌'} |
| RMSE (kg/ha) | {tr_rmses.mean():.1f} | {tr_rmses.std():.1f} | {te_rmses.mean():.1f} | {te_rmses.std():.1f} | — | — |

> 旧 RMSE 阈值 0.0055 已作废：那是 normalized y 上的指标，本次 target 单位为 kg/ha（≈3700 量级）。

## SHAP Top 5（10 种子 mean|SHAP| 平均）
{shap_lines}

期望 Top 3（申报书 §1.3）：`irr > flood > sun`
实测 Top 3：`{' > '.join(top3_actual)}`    {'✅ 一致' if match else '⚠️ 不一致'}

## 代表模型
- 保存的 `xgb_model.pkl` / `scaler.pkl` 来自 **seed = {representative_seed}**
  （test R² {representative_te_r2:.4f}，最贴近 10 种子中位数 {median_r2:.4f}）
- 全部 10 个 seed 的完整结果见 `xgb_seeds_results.json`

## 与申报书对照
- 申报书 §3.1 硬指标 R² ≥ 0.62 → **mean test R² = {te_r2s.mean():.4f}** {'✅ 远超' if te_r2s.mean() >= 0.62 else '❌'}
- 申报书 §1.3 期望 SHAP Top-3 顺序 → {'✅ 一致' if match else f'⚠️ 实测为 {" > ".join(top3_actual)}'}

## 背景
本基线为 `project_v3_real_yield_finding.md` **路线 E 第 1 项**：在真实单产（而非王天硕 PR 前已煮熟的 Y）上的 XGB 基线。
对照消融 `y_butter` 残差另起脚本；LSTM 基线（路线 E 第 2 项）需同步重训。

## 状态
{'✅ 基线通过申报书硬指标，可作为下游 LSTM / Attention-LSTM 的参照。' if passed else '❌ 未达硬指标，需排查。'}

> ⚠️ 注意：`feature_columns.json` 现在是 11 列（原 10 列）；若 `backend/inference.py` 仍按 10 列硬编码，需要同步更新。
"""
(MODELS_DIR / "model_card.md").write_text(model_card)

for f in [
    "xgb_model.pkl",
    "scaler.pkl",
    "feature_columns.json",
    "xgb_seeds_results.json",
    "model_card.md",
]:
    p = MODELS_DIR / f
    print(f"  ✓ {f}  ({p.stat().st_size:,} bytes)")

print()
print("=" * 72)
print("XGBoost 基线（v3）完成。")
print("=" * 72)
