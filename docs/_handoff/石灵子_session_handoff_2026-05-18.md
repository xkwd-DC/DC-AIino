# 石灵子 session handoff · 2026-05-18

> 上一轮 Claude session 结束前的 handoff 笔记。
> 下次开新 Claude session 时第一件事：`git pull` + `gh pr view 11 --comments` + `gh issue view 9` + 读本文。

---

## 角色定位（新会话开局必读）

- **席位**：石灵子（数据工程） · cwd=`/home/darcy/DC/DC` · git 用户 `15934110986pmq-debug`
- **触发**：用户键入 `/remote-control SLZ` 或 `石灵子：...` 即我就位
- **工作流**：每轮 `git pull && gh issue view 9` 拿活 → 干 → 评论 / PR → schema 化 summary 回协调中心
- **跨 session 同步**：走 git + `docs/STATUS.md` + GitHub Issues/PR，**不走 memory**
- **协调中心**：`cwd=/home/darcy/DC`（潘妙齐 session），不在本 cwd

## 本轮（2026-05-17）做了什么

| 任务 | 状态 | 产物 |
|---|---|---|
| **D5** docs 数据集说明 v1 | ✅ PR #11 已开 | `docs/11_数据集说明_v1.md` 341 行 / 11 章 |
| **D7** MODIS / NASA POWER 月度可行性 | ✅ 评论已发 | Issue #9 comment 4470209866 |

## 关键决策

- **编号顺延**：spec doc 08 §12 原预留 `docs/09`，但 09/10 已被文献综述 + 域名备案占用，本轮顺延为 **`docs/11`**；PR body 已写明，等协调中心拍板是否要重排
- **月度可行性结论**：
  - ✅ MODIS NDVI/LST（已是月度，`modis_province_monthly.parquet`）+ NASA POWER（日度可 30min 聚合）
  - ⚠️ SPEI（当前仅年均，重跑 SPEIbase 月度版 ~2h）
  - ❌ y / irr / mech / fert / 灾害（统计年鉴年度发布，无月度）

## 仓库现状要点

| 文件 | 行 × 列 | 用途 |
|---|---|---|
| `data/interim/paper_panel_v3.parquet` | 403 × 27 · 0 NaN | **主交付**：11 维 X + 3 Y 候选 + 中间列 |
| `data/interim/modis_province_monthly.parquet` | 4836 × 14 · 0 NaN | MODIS 月度面板（31 × 156 月）|
| `data/interim/nasa_power_daily/*.csv` | 31 文件 × 4748 天 | NASA POWER 日度 2011-01-01 → 2023-12-31 |
| `data/interim/spei_province_annual.csv` | 31 × 13 | SPEI 年均 + 生长季均 |
| `data/raw/paper_panel/wang_tianshuo_original/*.xlsx` | 11 份 | 王原始 xlsx（含真实水旱灾面积，未接 panel）|

详细 schema / 缺陷 / 复现 / 合规 → `docs/11_数据集说明_v1.md`

## 8 条已知缺陷（按 v4 优先级）

1. **SPEI 派生 proxy**（影响 `flood` / `drou_a` / `flood_a`）— 王 xlsx 真实灾害已 ingest 未接 panel
2. **MODIS 未做耕地像元加权**（doc 08 §3.2 spec 偏离）— 当前是全省域均值
3. **CLCD 单年（仅 2022）** — 多年版本待补，Zenodo COG 流式策略已写
4. **sun 是辐射比近似** — `4380 × ALLSKY/CLRSKY`，Z-score 后等价（论文接受）
5. **NASA POWER 单点 ≠ 面均** — 省会经纬度单点 query，大省偏差
6. **Y 漂移已修复** — `y_wang_original` 跌 57%，重算用 `y_linear`
7. **LST 不进 11 维** — 保留为可选研究列
8. **栅格→省域聚合方法**：M1 验收 7 项硬指标过 6 项，此条 ❌

## 下一轮要看的（按优先级）

1. **PR #11 review 反馈**（协调中心 + 算法侧）
   - review 重点：11 维契约对齐 / 路线决策注脚措辞 / 已知缺陷 v4 优先级 / 编号 09 vs 11 / 合规署名
2. **D7 follow-up**：熊鑫如果要月度面板落地
   - offer：30min NASA POWER 月度 + 2h SPEI 月度 → `data/interim/multimodal_monthly_v0.parquet`
   - 给的建议 LSTM 设定：5 月度时变 X + 5 年度时不变 X + 年度 Y，月度 attention 加在物候期上
3. **v4 待办**（数据集说明 §6 v4 计划，非本轮 scope）：
   - SPEI proxy → 真实水旱灾面积
   - 耕地像元加权
   - 多年 CLCD（约 10 GB，COG 流式）
4. **M1 评审材料** 7-31 ddl

## 新会话起手命令

```bash
cd /home/darcy/DC/DC
git pull
gh pr view 11 --comments
gh issue view 9
cat docs/_handoff/石灵子_session_handoff_2026-05-18.md
cat docs/STATUS.md
```

## 新会话起手白话

> 我是石灵子席位（cwd=/home/darcy/DC/DC，数据工程），刚 git pull 完。
> 请读 `docs/_handoff/石灵子_session_handoff_2026-05-18.md` + `docs/STATUS.md`，
> 然后过 PR #11 的 review 反馈和 Issue #9 新派的活。
