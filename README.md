# 极端气候下粮食生产风险核心因子识别与韧性提升可视化决策系统

> **国家级大学生创新创业训练计划项目**(2026.06 – 2027.05)
> 多模态融合 · 三模型互补归因 · 三协议鲁棒性披露 · 决策支持系统作为核心交付

---

## 项目元信息

| 项 | 内容 |
|---|---|
| **项目类别** | 国家级大学生创新创业训练计划(创新训练)|
| **依托单位** | 山西农业大学 信息科学与工程学院 |
| **起止时间** | 2026 年 6 月 – 2027 年 5 月(12 月周期) |
| **经费** | 1 万元(内部消化,不申请追加)|
| **项目负责人** | **潘妙齐**(网络 2401)|
| **法定团队**(申报书 5 人) | 潘妙齐 · 熊鑫 · 石灵子 · 王天硕 · 张嘉越 |
| **实际开发团队**(4 人) | 潘妙齐 · 熊鑫 · 石灵子 · 常宇璇 |
| **指导教师** | 邱东芳(申报)· 徐苗(CRAIC 联合指导)|

> 法定团队 5 人为申报书已批准署名,不可改动;实际开发团队 4 人,常宇璇承担文档 / 可视化 / 大赛材料。详见 `docs/national/18_申报书_国家级批准版_2026-05-27.md`。

---

## 核心方法

**多模态融合数据集**:31 省 × 13 年(2011–2023)= 403 样本,11 维特征(气象 / 致灾 / 遥感 NDVI&LST / 统计 / GIS),目标 `yield_kg_per_ha`。详见 `docs/11_数据集说明_v1.md`。

**三模型互补归因**:XGBoost-SHAP(横截面非线性边际贡献)+ 基线 LSTM(时序对照)+ Attention-LSTM(softmax gating 内部偏好)。**核心创新不是追求三模型一致,而是诚实呈现归因分歧本身作为科学产出**——实测 XGB-SHAP 与 Attention-LSTM 在 11 维上的 Spearman ρ = **-0.055**(p=0.873),双视角互补而非一致性验证。

**三协议鲁棒性披露**(`backend/models/strict_cv_v3_card.md`):

| 验证协议 | R² | 含义 |
|---|---|---|
| random 8:2(论文协议) | **0.907 ± 0.038** | 省内因子相对重要性识别,可发表口径 |
| leave-year-out | **0.894 ± 0.104** | 时序泛化可用 |
| **leave-province-out 中位** | **-16.83**(31 省仅 1 省 R²>0) | **诚实披露 N=403/31 截面单位下空间外推上限** |

NDVI ablation:11→10 维 R² 损失仅 +0.003(NDVI 边际贡献 ≈ 0%)。所有对外材料严格遵守此口径——**不主张** "跨省高精度预测" / "SHAP × Attention 一致性验证" / "NDVI 是核心驱动",而是定位为"省内可解释归因 + 决策系统"。详见 `docs/AGENT_BRIEFING.md §4`。

---

## 系统功能(M01-M04)

四模块可视化决策支持系统,Vue 3 + Flask 3 + SQLite(demo)+ TensorFlow-CPU,单次推理 < 2 秒:

| 模块 | 视图 | 功能 |
|---|---|---|
| **M01** | `RiskMap.vue` | 风险时空地图 — 31 省年度风险等级地图 + 历史曲线(走 `/api/provinces?year=` + `/history`)|
| **M02** | `ShapDashboard.vue` | SHAP 归因看板 — 全局 / 单样本 11 维边际贡献(走 `/api/predict` top-N 真值染色)|
| **M03** | `ScenarioSim.vue` | 参数情景模拟 — 调整 5 维气象因子瞬时反馈风险变化 |
| **M04** | `ResiliencePath.vue` | 韧性路径推荐 — 12 条显式规则引擎合成 SHAP + Attention 双视角,差异化输出政策建议(走 `/api/predict` SHAP top + ensemble)|

系统已通过 a11y WCAG 2.2 AA + 6 个安全头(CSP / HSTS / XFO 等)+ rate-limit。规则引擎透明化披露见 `docs/17_韧性规则引擎说明.md`。

---

## 部署

- **公网域名**:[`grainrisk.app`](https://grainrisk.app)(即将上线,目标 6/25)
- **基础设施**:GCP e2-medium + nginx + gunicorn + certbot TLS
- **部署素材**:`deploy/nginx.conf` · `deploy/setup_letsencrypt.sh` · `backend/requirements.txt`

---

## 三主线进展(国家级结题硬指标:论文 / 软著 / 获奖 任一即过)

| 主线 | 状态 | 目标 |
|---|---|---|
| **A · 论文**(主推) | v1 初稿 §1/§3/§5/§6/§7 完成(`docs/papers/v1_draft.md`,478 行) | 首投《农业工程学报》(广电总局第一批,中文核心 EI),2026-12 投稿 |
| **B · 软著**(同步兜底) | 系统已 80%+ 实装,代码规模 6,284 行(远超 5K 阈值) | 9/30 提交申请,~3 月下证(项目负责人潘第一,**最稳兜底**)|
| **C · AI 大赛**(upside) | CRAIC 已提交(5/23)· AI 大赛准备中 | 省银及以上才计入硬指标 |

期刊验证:《农业工程学报》《中国生态农业学报》《地理研究》3/3 中文核心**全在广电总局第一批**;SCI 外刊(*Comp & Electronics in Agri* / *Ecological Informatics*)**不在名单**,仅 upside。详见 `docs/22_国家级要求总结_2026-05-27.md`。

---

## 仓库结构与文档索引

```
.
├── backend/       Flask 3 后端(API + 模型推理 + SHAP)
├── frontend/      Vue 3 前端(M01-M04 四模块)
├── data/          多模态数据集(paper_panel_v3 + MODIS + GIS + CLCD)
├── deploy/        GCP 部署素材(nginx + certbot)
├── scripts/       训练与 ETL 脚本(retrain_all.sh)
├── docs/          项目文档(执行计划 / 论文 / 申报书 / 鲁棒性报告)
└── notebooks/     探索性分析与模型实验
```

### 关键文档(按时序)

| 编号 | 文档 | 用途 |
|---|---|---|
| `AGENT_BRIEFING.md` | Agent 必读 | 所有 subagent 起手必读,§4 是叙事生死线 |
| `STATUS.md` | 实时大盘 | 项目级 single-source-of-truth,每次进展更新 |
| `00` | 项目执行计划 v2 | 4 人队 + 1 万经费 + 三模型互补 + GCP/SQLite |
| `11` | 数据集说明 v1 | paper_panel_v3 字段口径 |
| `12` | 系统开发执行计划 | Phase 0-5 系统建设节奏 |
| `13` | **国家级升级执行规划** | 三主线 + 12 月时间表 + 本周事 + 风险缓解 |
| `15` | 训练复现指南 | 熊鑫 pipeline reproducibility(环境 lock + retrain 脚本) |
| `16` | v4 数据扩展计划 | 8a 致灾真实源 + 8b 耕地像元权重 + 8c 多年 CLCD |
| `17` | 韧性规则引擎说明 | M04 12 规则透明化披露 |
| `22` | **国家级要求总结** | 结题硬指标 + 期刊清单验证 + 三主线再校准 |
| `23` | 软著申请材料指南 | 9/30 兜底提交时间倒推 |
| `national/18-21` | 国家级法定材料 | 申报书 N4 / 结题验收要求 / 广电总局期刊清单 |
| `papers/v1_draft.md` | 论文 v1 正文初稿 | 主线 A 核心交付 |

---

## 快速开始

```bash
# 后端
cd backend
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
gunicorn -b 127.0.0.1:5000 app:app

# 前端
cd frontend
npm install
npm run dev

# 模型复现(详见 docs/15)
bash scripts/retrain_all.sh
```

更详细的环境约束(`/tmp/dc-*` venv 路径、训练 artifact 白名单等)见 `docs/AGENT_BRIEFING.md §2`。

---

## 许可证与致谢

私有仓库,未经授权禁止使用。

致谢:邱东芳老师(申报指导)· 徐苗老师(CRAIC 联合指导)· 山西农业大学信息科学与工程学院。
