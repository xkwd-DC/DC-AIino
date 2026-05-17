# 数据采集 session · Kickoff Prompt

> 复制下面 `--- BEGIN ---` 到 `--- END ---` 之间的内容，粘贴到新开的 Claude Code session（在 `/home/darcy/DC/DC` 目录下启动）。

---

--- BEGIN ---

你接手的是「极端气候下粮食生产风险」省级大创项目的**数据采集实装**任务。本 session 的唯一职责是**写下载/聚合/对齐脚本**，跑通从原始数据 → 多模态面板的 pipeline。

## 上下文（必读）

- 工作目录：`/home/darcy/DC/DC`
- 任务交接文档：`docs/08_数据采集任务_石灵子.md` ← **先读这个**，里面有 schema、列名、单位、验收标准
- 数据目录骨架已建好：`data/raw/{modis_ndvi,modis_lst,gis_province,gis_cropland}/`、`data/interim/`、`data/processed/`
- 数据目录说明：`data/README.md`
- 另一个 session（潘妙齐的实装席位）做后端 / 论文 / 模块 C，**它不动 data/ 和 scripts/data/，所以你来写**

## 要做的事

按 doc 08 §4 / §5 / §6 实装三个脚本：

1. **`scripts/data/01_download_modis.py`** — NDVI（首选 geodata.cn 月度 1km 2001-2024）+ LST（首选 AppEEARS 或 MOD11C3）
2. **`scripts/data/02_aggregate_to_province.py`** — 用 CLCD 耕地掩膜 × 省界 zonal_stats → `data/interim/modis_province_monthly.parquet`
3. **`scripts/data/03_align_panel.py`** — 与论文已有面板按 `province × year` 对齐 → `data/processed/multimodal_panel_v1.parquet`

外加一个 EDA notebook：`notebooks/data/00_modis_eda.ipynb`

## 关键约束（不要踩雷）

1. **schema 别改**：输出列名/单位/省名约定看 doc 08 §3.2 / §3.3，下游（熊鑫训练 + 后端 API）已经依赖这套
2. **后端不要碰**：`backend/` 目录是潘妙齐的，11 个特征字段已 fix
3. **省界双源**：处理用天地图 GS(2024)0650（CGCS2000/WGS84），前端 UI 才用 DataV（GCJ-02 坐标偏移，**绝对不能用于栅格统计**）
4. **耕地逐年掩膜**：CLCD 是 1985-2023 逐年的，每个 MODIS 年份用对应那一年的，不要一张 2020 用到底
5. **环境隔离**：GDAL/rasterio 系建独立 conda env `data-pipeline`，不要污染 `backend/.venv`

## 推荐起步顺序

1. 先 `Read docs/08_数据采集任务_石灵子.md` 通读
2. 验证 conda 环境：`conda create -n data-pipeline python=3.10 gdal rasterio geopandas rioxarray earthaccess rasterstats xarray pandas pyarrow`
3. 小样本跑通：用河南 1 省 + 2022-07 一个月，端到端走通 MODIS HDF → NDVI mean，再扩到全部
4. 跑通后再扩到 31 省 × 156 月

## 备选工具

- 用户问过 [Scrapling](https://github.com/D4Vinci/Scrapling) 是否有用——结论是 90% 数据源有官方 API（earthaccess / Zenodo 直链 / DataV REST），**不需要**。仅当 geodata.cn 没暴露稳定下载直链时，可以用 `requests + session` 维持登录态拉文件，仍然不需要 Scrapling 的指纹伪装
- 国内 Earthdata 慢可以走 GEE Python API（社区版 150 EECU-小时/月配额够用）

## 验收

- M1 评审 **2026-07-31**，硬指标：31 省 × 156 月、时空对齐准确率 ≥ 95%、Parquet 格式、metadata.json 配套
- doc 08 §2 是完整验收清单

写完一个脚本就让我用河南 2022 的基准数据 sanity check 一遍再写下一个。开始之前先读 doc 08 通读，然后告诉我你的实施顺序和环境状态。

--- END ---

---

## 给潘妙齐 session（本 session 起草此文档的那个）的备忘

新 session（石灵子的数据采集席位）跑起来后，潘妙齐 session 继续：
- 每周日例会前，从石灵子拉进度 → 整合到周报
- 当数据列 schema / 单位 / 命名出现争议时，由潘统一裁决（已在 `backend/services/inference.py` 锁了 11 列）
- M1 评审前一周（2026-07-24 那周），起 PR review 流程
- 后端 / 论文 / 模块 C / 部署属于潘 session，**不动 data/ 和 scripts/data/**
