# paper_panel v4 数据扩展计划 outline (T8)

> **版本**：v4 plan outline（W22 起草，2026-05-26）
> **作者**：石灵子（数据工程）
> **关联**：`docs/13` §3 T8 / §0.2 G8 ｜ `docs/11` §6 + §10 v4 待办 ｜ `docs/AGENT_BRIEFING.md` §4
> **状态**：计划态 — 本周仅交付 outline；6/01 起执行；8/31 前 v4 final 入库
> **约束**：不阻塞 T5（GCP 上线）/ T6（训练复现）/ T7（论文 §3·§5·§6·§7）/ 9.30 软著；仅阻塞论文 §2 数据章 + §4 实验章

---

## 0. 一句话

v3 → v4 做三件事：① **灾害代理 → 真实统计源**（8a），② **MODIS 全省域均值 → 耕地像元加权**（8b），③ **CLCD 单年 → 2011-2023 逐年**（8c）。头条 R² 不期望大涨（N=403 上限未突破），但 SHAP / Attention 重要性结构会重排，让论文 §5 因子归因更可解释、§2 数据章口径与公开数据源一致。

---

## 1. 三方向详解

### 1.1 8a · 致灾因子细化 + 单位校核

#### 当前问题
来自 `docs/11` §6.1 + Issue #23：

- `flood` / `flood_a` / `drou_a` 三列在 v3 中都是 SPEI 派生 proxy：`flood = flood_a = max(0, SPEI×30)`，`drou_a = max(0, -SPEI×30)`，单位"千公顷"是代理值而非真实受灾面积
- 三列与 `spei` 高度共线 → SHAP 会把灾害贡献摊薄到 `spei` 上，因子归因可解释性下降
- Issue #23 红旗：`sun (h·a⁻¹ 近似)` / `prec (mm·a⁻¹)` / `flood_a (千公顷)` 单位一致性需要审计与补元数据

#### 数据源

| 源 | 介质 | 覆盖 | 来源 / 路径 |
|---|---|---|---|
| 《中国水旱灾害公报》详细版 | PDF 扫描 + 近年 Excel | 2011-2023 | 水利部官网 + 学校图书馆纸质本 |
| 中国农业灾害分布数据集 | csv / Excel | 2011-2023（待确认） | 中科院资环所 / 国家青藏高原科学数据中心 |
| 国家统计局《灾害基本情况》 | 王天硕 xlsx 已 ingest | 2011-2023 | `data/raw/paper_panel/wang_tianshuo_original/` |

#### 字段清单（v4 新增 / 改造）

| 字段 | 单位 | 含义 | 来源 | v3 状态 |
|---|---|---|---|---|
| `flood_a`（改造） | 千公顷 | 水灾受灾面积（真实） | 王 xlsx + 公报交叉 | SPEI 代理 |
| `flood_severe_a`（新增） | 千公顷 | 水灾成灾面积 | 王 xlsx + 公报 | — |
| `inund_a`（新增，如有） | 千公顷 | 内涝面积亚类 | 公报 / 农业灾害分布 | — |
| `drou_a`（改造） | 千公顷 | 旱灾受灾面积（真实） | 王 xlsx + 公报 | SPEI 代理 |
| `drou_severe_a`（新增） | 千公顷 | 旱灾成灾面积 | 王 xlsx + 公报 | — |
| `lodge_a`（新增，可选） | 千公顷 | 倒伏受灾面积（如有） | 公报 / 农业灾害分布 | — |
| `prec_50mm_days`（新增） | 日数 | 年内日降水 ≥ 50mm 日数 | NASA POWER daily（已有） | — |
| `spei`（保留） | std | SPEI 年均（与 8a 灾害解耦后作独立气候指标） | CSIC SPEIbase | 已有 |
| `flood`（废弃） | — | 与 `flood_a` 同义，删除 | — | 删 |

#### 工作量评估：5-8 工作日

| 子任务 | 估时 | 说明 |
|---|---|---|
| 公报扫描 + OCR（Tesseract / PaddleOCR）+ 双人校对 | 2-3 天 | PDF 扫描件质量参差，需 spot-check |
| 农业灾害分布数据集 ingest + 字段映射 | 1 天 | 字段清单确认 + 编码统一 |
| 单位统一审计（Issue #23 关闭） | 1 天 | 补 `paper_panel_raw_metadata.json` 字段单位 |
| 重 join 进 `paper_panel`，sanity check（灾害面积 vs SPEI 相关性） | 1-2 天 | 旧 proxy vs 新真实值的相关性须 > 0.5 才合理 |

---

### 1.2 8b · MODIS 耕地像元加权聚合

#### 当前问题
来自 `docs/11` §6.2：

- `scripts/data/05_aggregate_modis_to_province.py` v0 标注"没做耕地 mask"，省域聚合是全省域均值
- 含大量非耕地（沙漠 / 高原 / 林地 / 水体 / 城市）的省份（新疆 / 青海 / 西藏 / 内蒙）NDVI 系统性偏低
- 农业大省（河南 / 山东 / 安徽 / 江苏）影响较小，但全国一致采用面积加权才是论文可发表口径

#### 数据源
武大 Yang & Huang CLCD v01 30m 耕地栅格：
- 已下载：`data/raw/gis_cropland/CLCD_v01_2022_albert.tif`
- 投影：Albers Equal-Area (CGCS2000)
- 引用：Yang, J. & Huang, X. (2021). *ESSD*, 13, 3907-3925.

#### 改造方案

1. 新增脚本 `scripts/data/05b_modis_cropland_weighted.py`
2. **投影对齐**：CLCD（Albers, 30m）→ MODIS sinusoidal（1km）重投影 + 按 30m 像元落入 1km MODIS 像元的比例计算耕地占比栅格（cropland_ratio raster）
3. **聚合公式**：
   ```
   NDVI_province_month = Σ(NDVI_pixel × cropland_ratio_pixel × area_pixel)
                       / Σ(cropland_ratio_pixel × area_pixel)
   ```
4. 重跑 31 省 × 156 月 NDVI + LST 月度聚合
5. 输出：`data/interim/modis_province_monthly_v4.parquet`（替换 v3 `modis_province_monthly.parquet`）

#### 字段清单

| 字段 | 变化 |
|---|---|
| `ndvi`（改造） | 全省域均值 → 耕地像元加权均值 |
| `ndvi_summer_peak`（改造） | 同上 |
| `lst_day_growing_mean_k`（改造） | 同上 |
| `lst_night_growing_mean_k`（改造） | 同上 |
| `cropland_pixel_ratio`（新增，诊断列） | 省域内耕地像元占比 |
| `valid_pixel_ratio`（保留） | QA 过滤后保留像元比，与耕地权重独立 |

#### 工作量评估：3-5 工作日

| 子任务 | 估时 | 说明 |
|---|---|---|
| GDAL / rasterio 环境配置（`/tmp/dc-v4` venv） | 0.5 天 | 遵守 AGENT_BRIEFING §2 环境约束 |
| CLCD Albers → MODIS sinusoidal 重投影脚本 + 1 省 1 月 sanity | 1 天 | 关键风险点，须可视化对齐验证 |
| 耕地像元掩膜聚合脚本 + 单测（1 省 1 月） | 1-2 天 | pytest 覆盖：边界省份 / 干旱省份 / 农业大省 |
| 重跑 31 省 × 156 月 NDVI + LST 聚合 | 1 天 | CPU bound，多进程可并行减半 |

#### 预期影响
- 干旱 / 山地省份（新疆 / 青海 / 西藏 / 内蒙）NDVI 显著上升（剔除沙漠 / 高原稀疏植被）
- 农业大省（河南 / 山东 / 安徽 / 江苏）NDVI 变化较小（耕地占比本来就高）
- 整体重排省间 NDVI 排序，影响 SHAP 的 baseline 区分能力 → 头条 R² 不大动，但 NDVI 在 SHAP top-3 中的位置可能后退

---

### 1.3 8c · 多年 CLCD 替换单年

#### 当前问题
来自 `docs/11` §6.3：

- 仅 CLCD 2022 一年，套到 2011-2023 全周期
- 东北开荒（黑龙江 / 吉林 / 辽宁）、南方退耕（浙江 / 福建 / 广东）的耕地分布变化信号被冲掉
- 2022 套到 2011 会高估当时耕地面积（开荒方向）或低估（退耕方向）

#### 数据源
CLCD v01 2011-2023 年度快照：
- 来源：Zenodo（COG 流式可选）
- 总大小：约 10 GB（13 年 × ~700 MB）
- 引用：同 8b（Yang & Huang, 2021）

#### 改造方案

1. `scripts/data/01_download_cropland.py` 改 `--year` 接 2011-2023 全部年份（或 COG 流式按需读 chunk）
2. 8b 脚本扩展：每年聚合使用对应年份 CLCD（year=2011 → 2011 CLCD，year=2015 → 2015 CLCD，…）
3. 输出：`paper_panel_v4` 的 `ndvi` / `lst_*` 列每年权重栅格不同
4. 新增 `cropland_pixel_ratio` 变成 year × province 二维（而非 v3 单一 2022 套全周期）

#### 字段清单
与 8b 一致，但 `cropland_pixel_ratio` 从 31 省静态值变为 31 省 × 13 年动态值。

#### 工作量评估：2-3 工作日

| 子任务 | 估时 | 说明 |
|---|---|---|
| CLCD 2011-2023 下载（~10 GB） | 0.5-1 天 | Zenodo 限速 + 学校机房网，COG 流式可省盘 |
| 8b 脚本扩展（按年份选 CLCD 栅格） | 0.5 天 | 仅改 1 个参数化逻辑 |
| 重跑全部 31 省 × 13 年 × 12 月聚合 | 1 天 | 多进程并行 |

#### 预期影响
- 东北（黑龙江 / 吉林 / 辽宁）NDVI 趋势变得更陡（开荒方向）
- 南方部分省份（浙江 / 福建 / 广东）NDVI 趋势变得更平 / 略降（退耕方向）
- 整体提供 ~2-5% 的年度耕地分布精细化，影响 §4 时序泛化实验的稳健性

---

## 2. v4 vs v3 字段 diff 表（总览）

| 类别 | v3 | v4 | 影响 |
|---|---|---|---|
| 灾害列 | 3 列（`flood` / `flood_a` / `drou_a`）全是 SPEI 代理 | 5-7 列真实灾害（受灾 + 成灾 + 拆 `inund_a` / `lodge_a`） | 解耦 SPEI 与灾害，SHAP 共线性下降 |
| MODIS 聚合 | 全省域均值 | 耕地像元加权 | 干旱省份 NDVI 上升，省间 baseline 重排 |
| CLCD 时间 | 单年 2022 套全周期 | 多年 2011-2023 逐年 | 耕地分布趋势还原 |
| 单位与元数据 | `sun` / `prec` / `flood_a` 单位一致性未审（Issue #23） | 单位统一 + `paper_panel_raw_metadata.json` 字段元数据完整 | 论文 §2 表格 / 答辩可读性 |
| 暴雨日数 | 无 | `prec_50mm_days` 新增 | 极端天气信号补强（NASA POWER daily 已有，零边际成本） |
| 11 维契约 | 锁定 11 列 → `feature_columns.json` | **可能扩到 12-14 列** | 后端 `/api/predict` 需重训 / 加白名单，与熊鑫协调时机 |

---

## 3. 时间表（3 个月主战场，8/31 硬截止）

| 时段 | 主要任务 | 交付 |
|---|---|---|
| **6/01 – 6/30** | 8a 灾害数据采集 + OCR + 单位审计 | 真实 `flood_a` / `drou_a` / 衍生列 ingest 进 panel；Issue #23 关闭 |
| **7/01 – 7/15** | 8b 脚本开发（用 CLCD 2022 单年做 sanity） | `scripts/data/05b_modis_cropland_weighted.py` v0 跑通 1 省 1 月 |
| **7/15 – 7/31** | 8c CLCD 2011-2023 下载 + 集成 8b（年份参数化） | `modis_province_monthly_v4.parquet` 候选版 |
| **8/01 – 8/15** | 重跑全 31 省 × 156 月聚合 + v4 整合 | `paper_panel_v4.parquet` 候选版（403 × ~30 列） |
| **8/16 – 8/25** | 验证（跑 XGB / LSTM / Att-LSTM 三模型对比）+ diff 报告 | `paper_panel_v4.parquet` final + 本文档 §5.3 验证报告续作 |
| **8/26 – 8/31** | 接论文 §2 数据章 + §4 实验章 + 缓冲 / debug | `docs/11_数据集说明_v2.md` 起稿；论文 §2/§4 接 v4 数据 |

**总工作量**：12-19 工作日，跨 13 周日历周（考虑课业 + 期末并发，按 part-time 节奏约 6-7 周）。

---

## 4. 风险与依赖

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 公报 PDF 扫描质量差 → OCR 误差 | 8a 灾害数据脏 | 双人校对 + 与王 xlsx 国统口径交叉验证；OCR 误差 > 5% 的省份回退到手工录入 |
| R2 | 农业灾害分布数据集字段不全 | `lodge_a` / `inund_a` 拆不出来 | 维持当前粒度，列标 "如有 → 值；否则 NaN"；不强求 v4 必拆所有亚类 |
| R3 | GDAL / rasterio 环境配置 | 8b 起不动 | `uv venv /tmp/dc-v4` + 文档化依赖（遵守 AGENT_BRIEFING §2）；跑通 1 省 1 月 sanity 后再扩 |
| R4 | CLCD Albers vs MODIS sinusoidal 投影对齐 | 像元错位 → 聚合 NDVI 错 | `rasterio.warp.reproject` + nearest-neighbor + 1 省 1 月可视化 sanity（QGIS 叠加查对） |
| R5 | CLCD 2011-2023 Zenodo 限速 / 10GB 占用 | 8c 卡时间 | 学校机房网 + COG 流式（按需读 chunk，不全量落盘） |
| R6 | 11 维 → 12-14 维契约扩展 | 后端 `/api/predict` 需要重训，影响 T5 GCP 上线 / T6 训练复现 | `feature_columns.json` PR 单独提；与熊鑫协调 retrain 时机，论文 §4 实验前完成即可；T5/T6 主线不停 |
| R7 | 论文 §2/§4 阻塞 | 论文 12/31 投稿延后 | 8/31 硬截止；若 8a 延期 → §2 可分阶段写（先写 MODIS / CLCD，后补灾害），§4 实验等 8b/8c 完成即可 |
| R8 | 9.30 软著兜底硬指标 | 不依赖 v4 | 软著基于系统 + v3 数据；v4 是论文核心，非软著核心 |

---

## 5. 验证策略

v4 数据 ingest 完成后，复用熊鑫已固化的 retrain pipeline（`scripts/retrain_all.sh`，详见 `docs/15`），跑 XGB / LSTM / Att-LSTM 三模型 v4 vs v3 对比。

### 5.1 关键诊断指标（预期）

| 协议 | v3 R²（实测） | v4 R² 预期 | 解读 |
|---|---|---|---|
| random 8:2（论文协议） | 0.907 | **持平或微动 (±0.02)** | N=403 截面上限未变；头条不会大涨 |
| leave-year-out | 0.8943 | 持平或微动 | 时序泛化与灾害真实化弱相关 |
| leave-province-out 中位 | **-16.83**（31 省仅 1 省 R² > 0） | **仍为负，可能略改善** | 空间外推上限仍由 N=31 省份决定，v4 不解决 |
| NDVI ablation ΔR² | -0.003 | **可能拉大到 -0.01 ~ -0.03** | 耕地加权后 NDVI 区分度可能略升（不再均值化沙漠 / 林地） |

### 5.2 因子重要性预期重排

不期望 R² 大涨 — 这是 **v4 的核心价值**：让因子归因结构更可解释，而不是让头条数字更好看。预期变化：

- **SHAP top-3**：NDVI 在 v3 是头条主导（baseline 省份区分能力强）；v4 耕地加权后，NDVI 区分能力被稀释 → **NDVI 头条 SHAP 重要性可能跌**；`drou_a` / `flood_a` 真实灾害取代 SPEI 代理，稀疏信号上升 → **真实灾害列上升**
- **Attention top-3**：v3 中 `drou_a` / SPEI 主导；v4 中预期仍由 `drou_a` 主导（与 SHAP 不一致）→ **验证 §5 SHAP × Attention 双视角互补（非一致性验证）在 v4 仍然成立**
- **SPEI**：与灾害列解耦后，SPEI 独立信号可能浮现（干旱强度而非干旱面积）

### 5.3 v4 验证报告内容（8/15 起草，本文档续作）

待 8/01-8/15 跑完数据后，本节追加以下内容：

- v4 vs v3 三模型 R² 对比表（random 8:2 / leave-year-out / leave-province-out 全部协议）
- SHAP top-3 重排表（v3 vs v4，按 |SHAP| mean 排序）
- Attention top-3 重排表（v3 vs v4）
- SHAP × Attention Spearman ρ 复算（v3 = -0.055 → v4 = ?）
- v4 数据下 `flood_a` (SPEI 代理 → 真实) 的归因变化定性诊断
- 论文 §4 实验段落初稿可基于此报告

---

## 6. 与其他主线的关系（阻塞 / 不阻塞矩阵）

| 主线 | 关系 |
|---|---|
| T6 训练复现（熊鑫，`docs/15`） | **不阻塞** — v3 数据已固化，retrain 脚本基于 v3；v4 完成后用同 pipeline retrain 一遍即可 |
| T7 论文 §3 方法 / §5 SHAP × Attention / §6 决策系统 / §7 局限 | **不阻塞** — 基于 v3 已起稿（`docs/papers/v1_outline.md`） |
| **T7 论文 §2 数据章 + §4 实验章** | **阻塞** — 等 v4 final（8/31）后定稿 |
| T5 GCP 上线（潘，6/25） | **不阻塞** — 后端 `/api/predict` 跑 v3 11 维契约不变 |
| 9.30 软著（潘） | **不阻塞** — 软著基于系统 + v3 数据 |
| 11 维 → 12-14 维契约扩展 | **协调** — 与熊鑫协调 `feature_columns.json` + 后端 schema，论文 §4 实验前完成即可 |
| AI 大赛（C 线，常宇璇 / 潘） | **不阻塞** — 大赛材料用 v3 数据 |

---

## 7. 叙事合规自查（AGENT_BRIEFING.md §4 守门）

本计划遵守以下表述纪律：

- ❌ 不写 "v4 让模型达到 R² > 0.95 高精度跨省预测"
- ❌ 不写 "v4 让 SHAP × Attention 一致性验证通过"
- ❌ 不写 "v4 证明 NDVI 是核心驱动因子"
- ❌ 不写 "v4 双重验证一致性"
- ✅ 写 "v4 把灾害特征从 SPEI 代理换成真实统计源，让 §5 因子归因更可解释"
- ✅ 写 "v4 头条 R² 不期望大涨（N=403 上限未突破）"
- ✅ 写 "v4 SHAP / Attention 重要性会重排，但仍是双视角互补（非一致性验证）"
- ✅ 写 "v4 不解决空间外推（leave-province-out 仍是负数 ceiling），那是 §7 未来工作三方向（县级 / 时序加长 / 混合效应）"

---

## 8. 状态与下一步

- **本周 W22**（5/26 – 5/31）：仅交付 outline（本文档），不动实际数据
- **W23 起**（6/01）：启动 8a 灾害数据采集 + OCR
- **8/31**：`paper_panel_v4.parquet` final 入库，论文 §2 数据章 + §4 实验章可接 v4 数据
- **关联 Issue**：G8（待新建，纳入 milestone "国家级升级"）；Issue #23（单位一致性）在 8a 完成时关闭

---

## 9. 关联文档

| 文件 | 用途 |
|---|---|
| `docs/11_数据集说明_v1.md` | v3 数据现状 + §6 已知缺陷（v4 三方向的 baseline） |
| `docs/13_国家级升级执行规划_2026-05-26.md` §3 T8 + §0.2 G8 | v4 在国家级规划中的位置 |
| `docs/_craic/robustness_summary_2026-05-22.md` | 鲁棒性事实（叙事红线来源） |
| `docs/AGENT_BRIEFING.md` §4 | 叙事守门规则 |
| `docs/15_训练复现指南.md` | v4 数据 ingest 后跑三模型用的 retrain pipeline |
| `scripts/data/README.md` | 数据 pipeline 复现指南（v4 新增脚本入此 README） |
| `data/interim/paper_panel_v3.parquet` | v4 改造起点 |

---

> 本文档 W22（2026-05-26）为计划 outline；v4 验证报告（实跑数据后）在 8/15 起追加 §5.3 内容；v4 final 入库后另起 `docs/11_数据集说明_v2.md` 替换 v1。
