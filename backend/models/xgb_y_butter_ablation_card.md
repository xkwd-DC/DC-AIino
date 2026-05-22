# Ablation Card — XGBoost on y_butter（方法学消融）

## 训练信息
- 训练日期：2026-05-17 10:23:21
- 训练人：熊鑫
- 数据源：data/interim/paper_panel_v3.parquet（MD5 前 12 位 `7f2070282216`）
- 协议：与主基线（`model_card.md`）完全一致 —— 11 维特征 / 10 种子 / 论文超参
- **唯一不同**：target = `y_butter`（Butterworth 残差，filtfilt order=2 fc=0.25）

## 角色
方法学消融，**不是交付模型**。为论文/报告里的「申报书 §2.3 #3 去趋势合规性」
论述提供实证背书。代表模型未保存（无下游使用价值）。

## 指标（10 种子）

| 指标 | 训练集 mean ± std | 测试集 mean ± std |
|---|---|---|
| R² | 0.9967 ± 0.0010 | -0.1015 ± 0.2763 |
| RMSE (y_butter 单位) | 4.8 ± 0.6 | 94.1 ± 14.9 |

各种子明细：
- seed=0: te_R²=-0.2588  te_RMSE=107.3
- seed=1: te_R²=-0.0393  te_RMSE=111.5
- seed=2: te_R²=+0.3687  te_RMSE=92.1
- seed=3: te_R²=+0.0016  te_RMSE=93.2
- seed=4: te_R²=+0.1255  te_RMSE=97.1
- seed=5: te_R²=-0.3320  te_RMSE=75.8
- seed=6: te_R²=-0.5979  te_RMSE=71.9
- seed=7: te_R²=-0.4110  te_RMSE=110.7
- seed=8: te_R²=+0.0354  te_RMSE=107.9
- seed=9: te_R²=+0.0924  te_RMSE=73.4

## 与主基线对照

| 维度 | 主基线 (yield_kg_per_ha) | 消融 (y_butter) | Δ |
|---|---|---|---|
| test R² mean | 0.9072118332865688 | -0.1015 | -1.0088 |
| 含义 | 真实单产可被特征预测 | 去趋势残差不可被特征预测 | — |

## 结论（写给申报书 §2.3 / 路线 E）

✅ **test R² mean = -0.1015 ≈ 0**，
而 **train R² mean = 0.9967**（train 能拟合，test 完全不泛化）。

这是申报书 §2.3 #3 去趋势方法在年聚合面板（N=403 = 31 省 × 13 年）+ 11 维
特征下的**实证表现**：

1. 去趋势方法本身（Butterworth filtfilt order=2 fc=0.25）正确实施 ——
   在真实单产（非王天硕已煮熟的 Y）上做的
2. 残差中**没有 generalizable 的特征驱动信号** —— 不是假设错了，
   是 N=403 + 11 维的样本量配置不足以从年聚合面板的残差中拟合稳定关系
3. 主报告路线（直接预测真实单产水平 `yield_kg_per_ha`，R² ≈ 0.90）
   是诚实地承认这个数据局限并给出有用模型的选择

## 与历史诊断的衔接

`project_xgb_baseline_diagnosis.md` 里"y_butter R²≈0"那段曾**作废**（因为在
王天硕坏 Y 上做的 Butterworth）。本消融用 v3 真实单产重做了同一实验，结论
反而**复活了那段诊断的核心观察**，但前提换了：从「方法或假设有问题」变成
「方法合规但样本量不足以从残差里抽信号」。

## 背景
路线 E 第 3 项（`project_v3_real_yield_finding.md`）：
- 第 1 项：XGB on yield_kg_per_ha → `model_card.md`
- 第 2 项：LSTM on yield_kg_per_ha → `lstm_model_card.md`
- **第 3 项：本消融** → 当前文件
