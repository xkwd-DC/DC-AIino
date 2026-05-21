# 训练 Cheat Sheet（熊鑫专用）

> **怎么用**：等潘的数据到位后，从上到下照单施工。
> 🟢 = 论文已实测，**照抄就行**
> 🟡 = 论文没明说，**你要自己定**（先用我建议值起步，调参时再优化）
> 🔴 = doc 07 的**验收硬指标**，达不到不能交付

---

## 0. 一句话目标

> 用 11 个气候/农业特征预测 31 省的粮食生产风险 Y，
> XGBoost 复现论文 R²=0.6293，LSTM 复现 R²=0.6619，Attention-LSTM 做到 R²≥0.65。

---

## 1. 数据 Pipeline（3 步走，对应 doc 07 任务 1.5/1.6/1.8）

| 步骤 | 怎么做 | 来源 |
|---|---|---|
| 缺失值 | 线性插值 `df.interpolate(method='linear')` | 🟢 论文 §3.2.1 |
| 去趋势化 | Butterworth 低通滤波分解 → 波动残差作 **Y** | 🟢 论文 §3.2.2 |
| 标准化 | Z-score（`StandardScaler`），**保存 `scaler.pkl`** | 🟢 论文 §3.2.3 |
| 划分 | 训练:测试 = **8:2** | 🟢 论文 §4.1 |

> ⚠️ Y 是**单产波动**不是绝对单产。论文 §3.1 公式：`R = |Y_实际 - Y_拟合|`，再用 Butterworth 滤波平滑成最终 Y。这个不能搞错。

---

## 2. 特征清单（11 个，固定）

| 训练列名（大写） | 中文 | 单位 | 论文均值 |
|---|---|---|---|
| Temp | 平均气温 | °C | 14.05 |
| SPEI | 干旱指数 | — | -0.08 |
| Prec | 降水量 | mm/年 | 754 |
| Sun | 日照时数 | h/年 | 2086 |
| Flood_R | 洪涝占比 | % | 2.97 |
| Drou_A | 旱灾受灾面积 | khm² | 316 |
| Flood_A | 水灾受灾面积 | khm² | 185 |
| Irr | 灌溉率 | % | 56.69 |
| Mech | 农机总动力 | 万 kW | 0.70 |
| Fert | 化肥施用量 | 万吨 | 179 |
| **NDVI** | 植被指数异常 | z-score | —（doc 07 新增） |

数据集规模：**N = 403**（约 31 省 × 13 年，论文 §3.3 表 3-2）

---

## 3. XGBoost 配方（论文超参全有，照抄）

```python
from xgboost import XGBRegressor

model = XGBRegressor(
    learning_rate=0.1,         # 🟢 论文 §4.1
    max_depth=6,               # 🟢 论文 §4.1
    n_estimators=150,          # 🟢 论文 §4.1（Grid Search 选出）
    objective='reg:squarederror',
    random_state=42,
)
# 论文没说但常见默认值，先用着，调参时再动
# subsample=1.0, colsample_bytree=1.0, gamma=0, reg_lambda=1
```

**期望成绩**：测试集 R² ≈ **0.6293**、RMSE ≈ **0.0051** 🟢

**🔴 验收门槛**：R² ≥ 0.62、RMSE ≤ 0.0055

---

## 4. SHAP 配方（3 张图必交，对应 doc 07 任务 2.3）

```python
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

shap.summary_plot(shap_values, X_test)              # 蜂群图（必交）
shap.dependence_plot('Irr', shap_values, X_test)    # 依赖图：灌溉率
shap.dependence_plot('Irr', shap_values, X_test,
                     interaction_index='Temp')      # 交互图：Irr × Temp 🟢 论文 §4.4
```

**期望发现**：Top 3 应该是 **Irr > Flood_R > Sun** 🟢（论文 §4.2）。
如果差太远，先排查数据是不是接对了。

---

## 5. LSTM 配方（论文只说了一半，另一半你自己定）

### 5.1 架构（论文已说）🟢

```
输入层 → LSTM 第 1 层 → LSTM 第 2 层 → Dropout → Dense(1)
优化器：Adam   损失：MSE   带 Dropout
```

### 5.2 关键超参（论文**没说**，🟡 给你建议起步值）

| 超参 | 建议起步值 | 说明 |
|---|---|---|
| timesteps（时间窗口长度） | **3 或 5** 年 | LSTM 看过去几年来预测当年；先用 5 试 |
| LSTM 每层 hidden_units | **64 → 32** | 第一层 64，第二层 32 |
| Dropout 率 | **0.2** | 0.1~0.3 都常见 |
| Batch size | **16** | 数据 N=403 小，batch 别太大 |
| Epochs | **100** | 加 EarlyStopping，patience=10 |
| Learning rate | **1e-3** | 不收敛就降到 1e-4（doc 07 §5.2 提醒过） |

```python
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping

model = Sequential([
    LSTM(64, return_sequences=True, input_shape=(timesteps, n_features)),
    LSTM(32),
    Dropout(0.2),
    Dense(1),
])
model.compile(optimizer='adam', loss='mse')
model.fit(X_train, y_train, epochs=100, batch_size=16,
          validation_split=0.2,
          callbacks=[EarlyStopping(patience=10, restore_best_weights=True)])
```

**期望成绩**：R² ≈ **0.6619**、RMSE ≈ **0.0046** 🟢
**🔴 验收门槛**：R² ≥ 0.62、RMSE ≤ 0.0055

### 5.3 ⚠️ 时间窗口（timesteps）这件事很重要

如果用 timesteps=5，每个样本的输入是 `(5, 11)`——过去 5 年的 11 个特征。
**但论文 N=403 是按"省-年"展开的**，意思是论文 LSTM 可能用了 timesteps=1（把 LSTM 当 MLP 用）。

先和潘对一句：**论文 LSTM 是不是用了滑动窗口？**
如果不是，timesteps=1 起步；如果是，按论文复现。

---

## 6. Attention-LSTM 配方（doc 07 §5.2 新工作）🟡

论文里**没有**这块，是你新做的。建议步骤：

1. 先复现普通 LSTM 拿到 R²≈0.66
2. 在第 2 层 LSTM 后加 `Attention` 层（Keras 内置 `tf.keras.layers.Attention`）
3. **不收敛时**：先冻结 LSTM 权重只训 Attention（`layer.trainable=False`），再联合训练
4. 输出注意力权重（attention scores）做可视化——这是论文级亮点

**🔴 验收门槛**：R² ≥ **0.65**（严于普通 LSTM）

---

## 7. 交付清单（doc 07 §3.1）

放 `backend/models/`（gitignored）：

- [ ] `xgb_model.pkl`（`joblib.dump`）
- [ ] `lstm_model.h5`（`model.save`）
- [ ] `attention_lstm.h5`
- [ ] `scaler.pkl`（StandardScaler，两个模型共用）
- [ ] `feature_columns.json`（11 个大写列名，顺序固定）
- [ ] `shap_explainer.pkl`（可选）
- [ ] `model_card.md`（训练日期、超参、指标、数据 hash）

交付前**必跑** `backend/services/inference.py` 的 sanity check：
```bash
/home/xxfql/DC-AIino/.venv/bin/python -m backend.services.inference
```
看到 `✅ PASS` 才算交付。

---

## 8. 常见坑（建议训练时贴在屏幕边）

| 现象 | 通常原因 | 怎么办 |
|---|---|---|
| LSTM Loss 不下降 | 学习率太大 | 1e-3 → 1e-4 |
| Attention 不收敛 | 联合训练梯度乱 | 先冻 LSTM 只训 Attention |
| 测试集 R² 比训练集低很多 | 过拟合 | 加 Dropout、减 hidden_units、加 EarlyStopping |
| XGBoost 训练分数高但测试垮 | 树太深 | max_depth 6 → 4，n_estimators 150 → 100 |
| SHAP 跑很慢 | TreeExplainer 没用对 | `shap.TreeExplainer(model)` 而不是 KernelExplainer |
| `.h5` 加载报"unknown layer Attention" | 自定义层没注册 | `load_model(..., custom_objects={'Attention': ...})` |
| 在后端加载报 numpy 版本错 | 训练用 numpy 2.x | 训练侧降到 numpy 1.26 与后端对齐 |
