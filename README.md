# 极端气候下粮食生产风险核心因子识别与韧性提升可视化系统

> 省级大学生创新创业训练计划项目（2026.05 – 2027.04）
> **项目负责人**：潘妙齐 | **指导教师**：邱东芳 | **经费**：1.5 万元

## 项目背景

在已完成的论文成果（XGBoost-SHAP 模型 R²=0.6293，LSTM 模型 R²=0.6619）基础上，构建：

- **多模态数据融合**：统计 + 气象 + 致灾 + MODIS 遥感 + GIS 矢量
- **Attention-LSTM 升级模型**：注意力机制加权时序聚合
- **Vue3 + Flask + PostgreSQL Web 可视化系统**：风险地图 / SHAP 看板 / 情景模拟 / 路径推荐
- **31 省差异化韧性提升路径报告**

## 仓库结构

```
.
├── docs/              项目文档（执行计划、论文、申报书、支撑材料）
├── data/              数据集（原始/中间/处理后；大文件用 Git LFS）
├── src/               源代码（数据处理、模型训练、API 后端、前端）
├── notebooks/         探索性分析与模型实验 Jupyter notebook
└── README.md
```

## 四阶段路线图

| 阶段 | 时间 | 里程碑 |
|---|---|---|
| 一 · 数据采集与预处理 | 2026.05 – 2026.07 | M1：多模态数据集 v1.0 |
| 二 · 双模型构建与验证 | 2026.08 – 2026.11 | M2：R² ≥ 0.62，RMSE ≤ 0.0055 |
| 三 · 可视化系统开发 | 2026.12 – 2027.02 | M3：在线 URL，推理 ≤ 2s |
| 四 · 成果整理与推广 | 2027.03 – 2027.04 | M4：结题答辩 + 论文/竞赛/软著 |

详见 [`docs/00_项目执行计划.md`](docs/00_项目执行计划.md)。

## 团队分工

| 成员 | 角色 | 主要负责 |
|---|---|---|
| **潘妙齐** | Tech Lead / 后端 / 论文 | 整体架构、Flask API、Attention 机制 |
| **石灵子** | 数据工程师 | MODIS 遥感、GIS 矢量、数据清洗 |
| **王天硕** | 算法工程师 / 数据库 | XGBoost-SHAP、PostgreSQL、韧性路径推荐 |
| **张嘉越** | 算法工程师 | LSTM、Attention-LSTM、模型轻量化 |
| **周煜楠** | 前端工程师 / UI | Vue3、Leaflet 地图、ECharts 看板 |
| **邱东芳** | 指导教师 | 周例会、技术指导、论文审阅 |

## 技术栈

- **数据**：Python 3.9+ / pandas / numpy / scipy / rasterio / GDAL / geopandas
- **模型**：XGBoost / SHAP / TensorFlow 2.x（或 PyTorch）/ MLflow
- **后端**：Python 3.10 / Flask 3 / Gunicorn / SQLAlchemy
- **数据库**：PostgreSQL 15
- **前端**：Vue 3 / Vite / Pinia / ECharts 5 / Leaflet / Element Plus
- **部署**：Docker / Nginx / 阿里云 ECS

## 许可证

私有仓库，未经授权禁止使用。
