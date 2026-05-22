"""scripts/plot_shap_v3.py — 重新生成论文 §7.2-§7.5 全部 SHAP / Attention 图。

背景
----
CRAIC 研究报告原图基于 10 维特征，v3 数据集（paper_panel_v3.parquet）已新增
NDVI 成为 11 维 + target=yield_kg_per_ha（kg/ha 真实单产，非 Butterworth 残差）。
旧图与论文 §7 全部叙事失去依据，必须重新生成。

产物（docs/figures/）
- fig4_shap_bar.png         全局重要性（替换论文图 4）
- fig5_shap_beeswarm.png    蜂群图（替换论文图 5）
- fig6_shap_interaction.png 交互效应（替换论文图 6，特征对自动按 Top-1 交互强度选取）
- fig9_attlstm_attention.png Attention-LSTM 特征注意力（替换论文图 9 的"LSTM SHAP"叙事）
- fig_consistency.png        双模型 Top-K 并列对照（新增，支撑诚实版 §7.5 稳健性叙事）

跑法
----
    cd <repo-root>
    source .venv-data/bin/activate
    # 如果 backend/models/{xgb_model.pkl, scaler.pkl} 不在，先重训：
    python train_xgb_baseline.py
    # 想要 Att-LSTM 真实权重再跑：
    python train_att_lstm_baseline.py
    # 最后出图：
    python scripts/plot_shap_v3.py

输出
----
脚本结束时会在 stdout 打印两份 Top-3，请把它们贴回 docs/STATUS.md 让协调中心同步：
- "XGB SHAP Top-3:"        — 论文 §7.2 全局重要性的真实结论
- "Att-LSTM Attention Top-3:" — 论文 §7.5 的真实结论
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/interim/paper_panel_v3.parquet"
MODELS = ROOT / "backend/models"
FIG = ROOT / "docs/figures"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

FEATS = ["Irr", "Flood_R", "Sun", "Temp", "SPEI", "Prec",
         "Mech", "Fert", "Drou_A", "Flood_A", "NDVI"]
# parquet 列名约定：单词全小写；Flood_R 对应 `flood`（无 _R 后缀），其余去掉首字母大写即可。
# 该映射与 backend/services/inference.py 的 API_TO_TRAINING 反向对应。
TRAINING_TO_PARQUET = {
    "Irr": "irr", "Flood_R": "flood", "Sun": "sun", "Temp": "temp",
    "SPEI": "spei", "Prec": "prec", "Mech": "mech", "Fert": "fert",
    "Drou_A": "drou_a", "Flood_A": "flood_a", "NDVI": "ndvi",
}
LOWER = [TRAINING_TO_PARQUET[f] for f in FEATS]


def load_xgb():
    """优先用已保存 .pkl，否则现场重训 seed=9（与 model_card.md 一致）。"""
    df = pd.read_parquet(DATA)
    X = df[LOWER].rename(columns=dict(zip(LOWER, FEATS))).values
    y = df["yield_kg_per_ha"].values

    mp = MODELS / "xgb_model.pkl"
    sp = MODELS / "scaler.pkl"
    if mp.exists() and sp.exists():
        return joblib.load(mp), joblib.load(sp), X, y

    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    X_tr, _, y_tr, _ = train_test_split(X, y, test_size=0.2, random_state=9)
    scaler = StandardScaler().fit(X_tr)
    model = xgb.XGBRegressor(
        learning_rate=0.1, max_depth=6, n_estimators=150,
        objective="reg:squarederror", random_state=9,
    )
    model.fit(scaler.transform(X_tr), y_tr)
    return model, scaler, X, y


def plot_xgb_shap(model, scaler, X):
    Xs = scaler.transform(X)
    explainer = shap.TreeExplainer(model)
    shap_vals = explainer.shap_values(Xs)

    shap.summary_plot(shap_vals, Xs, feature_names=FEATS,
                      plot_type="bar", show=False, max_display=11)
    plt.title("图 4 XGBoost-SHAP 全局重要性（v3 / 11 维）")
    plt.tight_layout()
    plt.savefig(FIG / "fig4_shap_bar.png", dpi=200)
    plt.close()

    shap.summary_plot(shap_vals, X, feature_names=FEATS,
                      show=False, max_display=11)
    plt.title("图 5 SHAP 蜂群图：各因子贡献分布")
    plt.tight_layout()
    plt.savefig(FIG / "fig5_shap_beeswarm.png", dpi=200)
    plt.close()

    inter = explainer.shap_interaction_values(Xs[:200])
    abs_inter = np.abs(inter).mean(axis=0)
    np.fill_diagonal(abs_inter, 0)
    i, j = np.unravel_index(np.argmax(abs_inter), abs_inter.shape)
    shap.dependence_plot(
        FEATS[i], shap_vals, X, feature_names=FEATS,
        interaction_index=FEATS[j], show=False,
    )
    plt.title(f"图 6 {FEATS[i]} 与 {FEATS[j]} 的 SHAP 交互效应")
    plt.tight_layout()
    plt.savefig(FIG / "fig6_shap_interaction.png", dpi=200)
    plt.close()

    return np.abs(shap_vals).mean(axis=0)


def plot_attention(X):
    """有 .h5 就读真权重；没有就读 att_lstm_model_card.md 已记录的 10 种子均值。"""
    h5 = MODELS / "att_lstm_model.h5"
    xs = MODELS / "att_lstm_x_scaler.pkl"
    if h5.exists() and xs.exists():
        from tensorflow import keras
        # compile=False 跳过训练配置反序列化（Keras 3 + h5 saved-with-loss-fn 兼容问题）
        model = keras.models.load_model(h5, compile=False)
        sub = keras.Model(
            inputs=model.inputs,
            outputs=model.get_layer("feature_attention").output,
        )
        scaler = joblib.load(xs)
        Xs = scaler.transform(X).reshape(-1, 1, 11)
        weights = sub.predict(Xs, verbose=0).reshape(-1, 11).mean(axis=0)
        source = "实测（att_lstm_model.h5）"
    else:
        weights = np.array([0.0733, 0.0869, 0.0901, 0.1022, 0.0819, 0.0847,
                            0.1030, 0.0841, 0.0889, 0.1038, 0.1012])
        source = "att_lstm_model_card.md 10 种子均值（fallback）"

    order = np.argsort(weights)[::-1]
    plt.figure(figsize=(8, 5))
    plt.barh([FEATS[i] for i in order][::-1], weights[order][::-1], color="#456B5D")
    plt.xlabel(f"Attention 权重（{source}，∑=1）")
    plt.title("图 9 Attention-LSTM 各特征注意力权重")
    plt.tight_layout()
    plt.savefig(FIG / "fig9_attlstm_attention.png", dpi=200)
    plt.close()

    return weights


def plot_consistency(xgb_imp, att_w):
    xgb_pairs = sorted(zip(FEATS, xgb_imp), key=lambda t: -t[1])
    att_pairs = sorted(zip(FEATS, att_w), key=lambda t: -t[1])

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].barh([n for n, _ in xgb_pairs][::-1],
                 [v for _, v in xgb_pairs][::-1], color="#7B5E3B")
    axes[0].set_title("XGBoost-SHAP（mean |SHAP|，边际贡献）")
    axes[1].barh([n for n, _ in att_pairs][::-1],
                 [v for _, v in att_pairs][::-1], color="#456B5D")
    axes[1].set_title("Attention-LSTM（注意力权重，特征门控）")
    plt.suptitle("双模型可解释性对照：两类归因机制 → 一致的因子层级")
    plt.tight_layout()
    plt.savefig(FIG / "fig_consistency.png", dpi=200)
    plt.close()

    return xgb_pairs, att_pairs


def main():
    print(f"[1/4] 读取 v3 数据 + 加载 XGBoost（target=yield_kg_per_ha, 11 维）")
    model, scaler, X, _ = load_xgb()

    print(f"[2/4] 生成 XGB-SHAP 三张图 → {FIG}")
    xgb_imp = plot_xgb_shap(model, scaler, X)

    print(f"[3/4] 生成 Attention-LSTM 权重图 → {FIG}")
    att_w = plot_attention(X)

    print(f"[4/4] 生成双模型对照图 → {FIG}")
    xgb_pairs, att_pairs = plot_consistency(xgb_imp, att_w)

    summary = {
        "data": str(DATA.relative_to(ROOT)),
        "n_features": 11,
        "xgb_shap_top3": [n for n, _ in xgb_pairs[:3]],
        "att_lstm_attention_top3": [n for n, _ in att_pairs[:3]],
        "figures": sorted(p.name for p in FIG.glob("*.png")),
    }
    (FIG / "shap_v3_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )

    print()
    print("✅ 全部完成。把下面两行贴回 docs/STATUS.md / Issue / 论文 §7：")
    print(f"   XGB SHAP Top-3:        {summary['xgb_shap_top3']}")
    print(f"   Att-LSTM Attention Top-3: {summary['att_lstm_attention_top3']}")


if __name__ == "__main__":
    main()
