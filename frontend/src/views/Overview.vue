<script setup lang="ts">
/**
 * M00 · 系统总览(Overview) — 国家级评审 landing page
 *
 * v6 叙事基线(参见 docs/AGENT_BRIEFING.md §4 与 docs/_craic/04_申报书_v6_rewrite_draft.md):
 *   - 三模型互补归因架构(XGB-SHAP + 基线 LSTM + Attention-LSTM)
 *   - 三协议鲁棒性透明披露(random 8:2 / leave-year / leave-province-out)
 *   - Spearman 秩相关 -0.055 体现方法论独立性,互补而非一致
 *   - 决策支持系统是核心交付,模型作为引擎不依赖空间外推
 *
 * 数据来源 (单一权威):
 *   - backend/models/strict_cv_v3_card.md       三协议 R²
 *   - backend/models/rank_corr_v3_card.md       Top-3 + Spearman ρ
 *   - backend/models/mixed_effects_v1_card.md   ICC = 0.97
 *   - docs/_craic/04_申报书_v6_rewrite_draft.md 叙事基线
 *
 * 视觉风格沿用 M01-M05:.page / .card / .eyebrow / .lead + tokens.css 变量。
 */
import { RouterLink } from 'vue-router'

// ── KPI 卡组(顶部 4 张) ──────────────────────────────────────────────────
interface KpiCard {
  readonly eyebrow: string
  readonly title: string
  readonly value: string
  readonly unit?: string
  readonly subtitle: string
  readonly tone: 'green' | 'amber' | 'risk' | 'blue'
  readonly aria: string
}

const KPIS: ReadonlyArray<KpiCard> = [
  {
    eyebrow: 'COVERAGE',
    title: '覆盖省份',
    value: '31',
    subtitle: '全国 100%(不含港澳台)',
    tone: 'green',
    aria: '覆盖省份 31 个,全国 100%,不含港澳台',
  },
  {
    eyebrow: 'SAMPLES',
    title: '数据样本',
    value: '403',
    subtitle: '11 维 × 13 年(2011-23)',
    tone: 'blue',
    aria: '数据样本 403 条,11 维特征 × 13 年',
  },
  {
    eyebrow: 'TRI-MODEL R²',
    title: 'random 8:2 协议',
    value: '0.907',
    subtitle: 'XGB 0.907 / LSTM 0.886 / Attention-LSTM 0.816(10 种子均值)',
    tone: 'amber',
    aria: '三模型 R² 在 random 8:2 协议下,XGBoost 0.907,LSTM 0.886,Attention-LSTM 0.816,10 种子均值',
  },
  {
    eyebrow: 'ROBUSTNESS',
    title: 'leave-province-out 中位',
    value: '−16.83',
    subtitle: '诚实披露空间外推上限(31 省仅 1 省 R²>0)',
    tone: 'risk',
    aria: 'leave-province-out 协议中位 R² 为负 16.83,诚实披露空间外推上限,31 省中仅 1 省 R² 大于 0',
  },
]

// ── 三模型互补 chip 数据 ─────────────────────────────────────────────────
interface FactorChip {
  readonly code: string
  readonly label: string
}

const XGB_TOP3: ReadonlyArray<FactorChip> = [
  { code: 'NDVI', label: '植被指数' },
  { code: 'Prec', label: '降水量' },
  { code: 'Temp', label: '平均气温' },
]

const ATT_TOP3: ReadonlyArray<FactorChip> = [
  { code: 'Drou_A', label: '旱灾面积' },
  { code: 'SPEI', label: '干旱指数' },
  { code: 'Temp', label: '平均气温' },
]

// ── 数据源融合状态进度条 ─────────────────────────────────────────────────
interface DataSource {
  readonly name: string
  readonly status: '已就绪' | '推进中'
  readonly pct: number
  readonly note?: string
}

const DATA_SOURCES: ReadonlyArray<DataSource> = [
  { name: '省级统计数据(年鉴 + 公报)', status: '已就绪', pct: 100 },
  {
    name: 'MODIS 卫星遥感(NDVI / LST)',
    status: '已就绪',
    pct: 100,
    note: 'v4 耕地像元加权 推进中 60%',
  },
  { name: '气象站点逐日观测(CMDC + SPEI)', status: '已就绪', pct: 100 },
  {
    name: 'GIS 空间矢量(CLCD + 行政区划)',
    status: '已就绪',
    pct: 100,
    note: 'v4 多年 CLCD 推进中 75%',
  },
]

// ── 鲁棒性透明披露 ──────────────────────────────────────────────────────
interface RobustnessItem {
  readonly label: string
  readonly value: string
  readonly desc: string
  readonly tone: 'green' | 'amber' | 'risk' | 'blue'
  readonly aria: string
}

const ROBUSTNESS: ReadonlyArray<RobustnessItem> = [
  {
    label: 'Random 8:2 R²',
    value: '0.907 ± 0.038',
    desc: '论文协议(已见省份近邻样本)',
    tone: 'green',
    aria: 'Random 8:2 协议 R² 为 0.907 加减 0.038,代表论文协议在已见省份近邻样本上的拟合能力',
  },
  {
    label: 'Leave-year-out R²',
    value: '0.894',
    desc: '时序泛化能力可用',
    tone: 'green',
    aria: 'leave-year-out 协议 R² 为 0.894,时序泛化能力可用',
  },
  {
    label: 'Leave-province-out 中位',
    value: '−16.83',
    desc: '空间外推上限,诚实披露',
    tone: 'risk',
    aria: 'leave-province-out 协议中位 R² 为负 16.83,空间外推上限,诚实披露',
  },
  {
    label: '混合效应 PoC ICC',
    value: '0.97',
    desc: '证 R²=0.907 中约 97% 由省份固定效应贡献',
    tone: 'amber',
    aria: '混合效应 PoC ICC 为 0.97,证明 R² 等于 0.907 中约 97% 由省份固定效应贡献',
  },
]

// ── Quick Access 卡组(M01-M05) ────────────────────────────────────────
interface QuickEntry {
  readonly code: string
  readonly title: string
  readonly desc: string
  readonly to: string
  readonly icon: string
  readonly accent: boolean
}

const QUICK_ENTRIES: ReadonlyArray<QuickEntry> = [
  {
    code: 'M01',
    title: '查看风险地图',
    desc: '31 省风险等级时空分布',
    to: '/risk-map',
    icon: '◉',
    accent: false,
  },
  {
    code: 'M02',
    title: '查询省份因子',
    desc: 'SHAP 贡献度精细化解析',
    to: '/shap',
    icon: '◈',
    accent: false,
  },
  {
    code: 'M03',
    title: '参数情景模拟',
    desc: '反事实预测推理 < 2s',
    to: '/scenario',
    icon: '⚙',
    accent: false,
  },
  {
    code: 'M04',
    title: '韧性路径推荐',
    desc: '一省一策政策建议',
    to: '/pathway',
    icon: '◊',
    accent: false,
  },
  {
    code: 'M05',
    title: '推演监控',
    desc: '三模型实时协同 trace',
    to: '/monitor',
    icon: '⟳',
    accent: true,
  },
]
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M00 · SYSTEM OVERVIEW</div>
      <h2>核心云图 · 系统总览</h2>
      <p class="lead">
        基于<b>三模型互补归因架构</b>(XGBoost-SHAP + 基线 LSTM + Attention-LSTM),
        覆盖 2011 – 2023 全国 31 省多模态数据;省级统计 × 卫星遥感 × 气象逐日观测 × GIS 矢量四源融合。
      </p>
    </header>

    <!-- ── KPI 卡组(顶部 4 张) ────────────────────────────────────── -->
    <div class="kpi-grid" role="region" aria-label="系统关键指标概览">
      <article
        v-for="k in KPIS"
        :key="k.eyebrow"
        class="kpi-card"
        :class="`tone-${k.tone}`"
        :aria-label="k.aria"
      >
        <span class="kpi-accent" aria-hidden="true"></span>
        <div class="kpi-eyebrow">{{ k.eyebrow }}</div>
        <div class="kpi-title">{{ k.title }}</div>
        <div class="kpi-value" role="text">{{ k.value }}</div>
        <div class="kpi-sub">{{ k.subtitle }}</div>
      </article>
    </div>

    <!-- ── 双列 grid · 01 三模型互补 + 02 数据源融合 ──────────────── -->
    <div class="dual-grid">
      <!-- 左列:01 · MODEL COMPLEMENTARITY -->
      <article
        class="card section-card"
        role="region"
        aria-labelledby="section-complementarity"
      >
        <div class="section-head">
          <div class="num">01 · MODEL COMPLEMENTARITY · 三模型互补</div>
          <h3 id="section-complementarity">三模型互补归因架构</h3>
          <div class="section-sub">方法论独立 + 互补归因 · 三种原理回答不同科学问题</div>
        </div>

        <div class="complement-row">
          <div class="model-block">
            <div class="model-head">
              <span class="model-name">XGB-SHAP</span>
              <span class="model-tag">数据驱动 · 边际贡献</span>
            </div>
            <div class="chip-row" role="list" aria-label="XGB-SHAP Top-3 因子">
              <span
                v-for="c in XGB_TOP3"
                :key="c.code"
                class="chip chip-xgb"
                role="listitem"
              >
                <span class="chip-code">{{ c.code }}</span>
                <span class="chip-label">{{ c.label }}</span>
              </span>
            </div>
          </div>

          <div class="model-block">
            <div class="model-head">
              <span class="model-name">Attention-LSTM</span>
              <span class="model-tag">模型 gating · 内部偏好</span>
            </div>
            <div class="chip-row" role="list" aria-label="Attention-LSTM Top-3 因子">
              <span
                v-for="c in ATT_TOP3"
                :key="c.code"
                class="chip chip-att"
                role="listitem"
              >
                <span class="chip-code">{{ c.code }}</span>
                <span class="chip-label">{{ c.label }}</span>
              </span>
            </div>
          </div>

          <div class="complement-footer">
            <span class="complement-icon" aria-hidden="true">⇌</span>
            <div class="complement-text">
              仅 <b>Temp</b> 重合 1/3 ·
              Spearman <span class="mono">ρ = −0.055</span>(p=0.873)
              <span class="complement-sep">→</span>
              <b class="claim">方法论独立性是优势,非失败</b>
            </div>
          </div>
        </div>
      </article>

      <!-- 右列:02 · DATA FUSION -->
      <article
        class="card section-card"
        role="region"
        aria-labelledby="section-fusion"
      >
        <div class="section-head">
          <div class="num">02 · DATA FUSION · 数据源融合状态</div>
          <h3 id="section-fusion">四源多模态融合就绪度</h3>
          <div class="section-sub">四类多模态异构数据已完成时空对齐</div>
        </div>

        <ul class="source-list">
          <li
            v-for="s in DATA_SOURCES"
            :key="s.name"
            class="source-item"
          >
            <div class="source-head-row">
              <span class="source-name">{{ s.name }}</span>
              <span class="source-status" :class="s.status === '已就绪' ? 'st-ok' : 'st-wip'">
                {{ s.status }} {{ s.pct }}%
              </span>
            </div>
            <div
              class="source-bar"
              role="progressbar"
              :aria-label="`${s.name} 就绪度`"
              :aria-valuemin="0"
              :aria-valuemax="100"
              :aria-valuenow="s.pct"
            >
              <span
                class="source-fill"
                :class="s.status === '已就绪' ? 'fill-ok' : 'fill-wip'"
                :style="{ width: s.pct + '%' }"
              ></span>
            </div>
            <div v-if="s.note" class="source-note">注:{{ s.note }}</div>
          </li>
        </ul>
      </article>
    </div>

    <!-- ── 03 · ROBUSTNESS TRANSPARENCY · 鲁棒性透明披露(v6 关键创新区) ── -->
    <article
      class="card robust-card"
      role="region"
      aria-labelledby="section-robust"
    >
      <div class="section-head">
        <div class="num">03 · ROBUSTNESS TRANSPARENCY · 鲁棒性透明披露</div>
        <h3 id="section-robust">三协议并行 + 混合效应分解 · 学术诚实路线</h3>
        <div class="section-sub">
          在 random 8:2 协议下报告论文级 R²,同步披露 leave-year / leave-province-out 严格协议结果。
          混合效应 PoC 提供 R²=0.907 来源的定量分解证据。
        </div>
      </div>

      <div class="robust-grid">
        <div
          v-for="r in ROBUSTNESS"
          :key="r.label"
          class="robust-item"
          :class="`tone-${r.tone}`"
          :aria-label="r.aria"
          role="text"
        >
          <div class="robust-label">{{ r.label }}</div>
          <div class="robust-value">{{ r.value }}</div>
          <div class="robust-desc">{{ r.desc }}</div>
        </div>
      </div>

      <div class="robust-footer">
        <span class="dot-amber" aria-hidden="true"></span>
        上限诚实披露 + 决策系统兜底 = v6 学术诚实路线。模型不依赖空间外推,
        <b>决策支持系统</b>对已见 31 省提供可解释 + 可情景模拟 + 可输出差异化路径的政策工具。
      </div>
    </article>

    <!-- ── 04 · QUICK ACCESS · 快速入口 ────────────────────────────── -->
    <article
      class="card quick-card"
      role="region"
      aria-labelledby="section-quick"
    >
      <div class="section-head">
        <div class="num">04 · QUICK ACCESS · 快速入口</div>
        <h3 id="section-quick">五大业务模块 · 一键直达</h3>
        <div class="section-sub">从风险地图到推演监控,完整业务闭环</div>
      </div>

      <div class="quick-grid">
        <RouterLink
          v-for="q in QUICK_ENTRIES"
          :key="q.code"
          :to="q.to"
          class="quick-entry"
          :class="{ accent: q.accent }"
          :aria-label="`进入 ${q.code} ${q.title}:${q.desc}`"
        >
          <div class="quick-head">
            <span class="quick-icon" aria-hidden="true">{{ q.icon }}</span>
            <span class="quick-code">{{ q.code }}</span>
          </div>
          <div class="quick-title">{{ q.title }}</div>
          <div class="quick-desc">{{ q.desc }}</div>
          <div class="quick-arrow" aria-hidden="true">→</div>
        </RouterLink>
      </div>
    </article>
  </section>
</template>

<style scoped>
.page {
  padding: 24px 32px 48px;
  max-width: 1480px;
  margin: 0 auto;
  animation: fadeUp var(--dur-slow) var(--ease-out) both;
}

/* ── page-head ──────────────────────────────────────────────────── */
.page-head {
  margin-bottom: 24px;
}
.eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--green);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.page-head h2 {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: 0.4px;
  margin-bottom: 8px;
}
.lead {
  font-size: 13px;
  color: var(--text-2);
  max-width: 960px;
  line-height: 1.7;
}
.lead b {
  color: var(--green-bright);
  font-weight: 600;
}

/* ── KPI 卡组(4 张) ──────────────────────────────────────────── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}
.kpi-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 18px 18px 20px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform var(--dur-fast), border-color var(--dur-fast);
}
.kpi-card:hover {
  transform: translateY(-2px);
  border-color: var(--border-strong);
}
.kpi-accent {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
}
.kpi-card.tone-green .kpi-accent { background: linear-gradient(90deg, var(--green-deep), var(--green-bright)); }
.kpi-card.tone-blue .kpi-accent { background: linear-gradient(90deg, var(--blue), var(--blue-bright)); }
.kpi-card.tone-amber .kpi-accent { background: linear-gradient(90deg, var(--amber), var(--amber-bright)); }
.kpi-card.tone-risk .kpi-accent { background: linear-gradient(90deg, var(--red-deep), var(--red-bright)); }

.kpi-eyebrow {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1.1px;
  margin-bottom: 8px;
}
.kpi-title {
  font-size: 12px;
  color: var(--text-2);
  margin-bottom: 12px;
}
.kpi-value {
  font-family: var(--font-mono);
  font-size: 36px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 10px;
  letter-spacing: -0.5px;
}
.kpi-card.tone-green .kpi-value { color: var(--green-bright); }
.kpi-card.tone-blue .kpi-value { color: var(--blue-bright); }
.kpi-card.tone-amber .kpi-value { color: var(--amber-bright); }
.kpi-card.tone-risk .kpi-value { color: var(--red-bright); }

.kpi-sub {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  line-height: 1.5;
  letter-spacing: 0.2px;
}

/* ── 双列 grid + section-card ─────────────────────────────────── */
.dual-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 20px;
}
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 18px;
}
.section-card {
  display: flex;
  flex-direction: column;
}
.section-head {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.section-head .num {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1px;
  margin-bottom: 4px;
}
.section-head h3 {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}
.section-head .section-sub {
  font-size: 11px;
  color: var(--text-2);
  line-height: 1.5;
}

/* ── 三模型互补 block ─────────────────────────────────────────── */
.complement-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.model-block {
  padding: 12px 14px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
}
.model-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
  gap: 12px;
  flex-wrap: wrap;
}
.model-name {
  font-family: var(--font-serif);
  font-size: 13px;
  font-weight: 600;
  color: var(--green-bright);
}
.model-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.4px;
}
.chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: var(--r-md);
  font-size: 11px;
  border: 1px solid;
}
.chip-xgb {
  background: rgba(160, 183, 133, 0.10);
  border-color: rgba(160, 183, 133, 0.32);
  color: var(--green-bright);
}
.chip-att {
  background: rgba(230, 182, 85, 0.10);
  border-color: rgba(230, 182, 85, 0.32);
  color: var(--amber-bright);
}
.chip-code {
  font-family: var(--font-mono);
  font-weight: 600;
  letter-spacing: 0.3px;
}
.chip-label {
  font-size: 10px;
  opacity: 0.78;
}

.complement-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(160, 183, 133, 0.06);
  border: 1px dashed rgba(160, 183, 133, 0.25);
  border-radius: var(--r-md);
  font-size: 11px;
  color: var(--text-2);
  line-height: 1.6;
}
.complement-icon {
  font-family: var(--font-mono);
  font-size: 18px;
  color: var(--green);
  flex-shrink: 0;
}
.complement-text {
  flex: 1;
}
.complement-text b { color: var(--green-bright); }
.complement-text .mono { font-family: var(--font-mono); color: var(--amber-bright); }
.complement-sep { color: var(--text-3); margin: 0 4px; }
.claim { color: var(--green-bright); }

/* ── 数据源融合 progress list ─────────────────────────────────── */
.source-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  list-style: none;
}
.source-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.source-head-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
}
.source-name {
  font-size: 12px;
  color: var(--text);
}
.source-status {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.4px;
  font-weight: 600;
}
.source-status.st-ok { color: var(--green-bright); }
.source-status.st-wip { color: var(--amber-bright); }
.source-bar {
  height: 6px;
  background: var(--bg-2);
  border-radius: 3px;
  overflow: hidden;
  border: 1px solid var(--border);
}
.source-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  transition: width var(--dur-slow) var(--ease-out);
}
.source-fill.fill-ok { background: linear-gradient(90deg, var(--green-deep), var(--green-bright)); }
.source-fill.fill-wip { background: linear-gradient(90deg, var(--amber), var(--amber-bright)); }
.source-note {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.2px;
}

/* ── 鲁棒性透明披露 ───────────────────────────────────────────── */
.robust-card {
  margin-bottom: 20px;
}
.robust-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.robust-item {
  padding: 14px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-left: 2px solid var(--border-strong);
  border-radius: var(--r-md);
}
.robust-item.tone-green { border-left-color: var(--green); }
.robust-item.tone-amber { border-left-color: var(--amber); }
.robust-item.tone-risk { border-left-color: var(--red); }
.robust-item.tone-blue { border-left-color: var(--blue); }
.robust-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.4px;
  margin-bottom: 8px;
}
.robust-value {
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 700;
  line-height: 1.05;
  margin-bottom: 8px;
  letter-spacing: -0.4px;
}
.tone-green .robust-value { color: var(--green-bright); }
.tone-amber .robust-value { color: var(--amber-bright); }
.tone-risk .robust-value { color: var(--red-bright); }
.tone-blue .robust-value { color: var(--blue-bright); }
.robust-desc {
  font-size: 11px;
  color: var(--text-2);
  line-height: 1.5;
}

.robust-footer {
  padding: 12px 14px;
  background: rgba(230, 182, 85, 0.06);
  border: 1px solid rgba(230, 182, 85, 0.22);
  border-radius: var(--r-md);
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.65;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.robust-footer b { color: var(--amber-bright); font-weight: 600; }
.dot-amber {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--amber);
  margin-top: 6px;
  flex-shrink: 0;
}

/* ── Quick Access ─────────────────────────────────────────────── */
.quick-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.quick-entry {
  position: relative;
  padding: 16px 14px 18px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  text-decoration: none;
  color: inherit;
  display: flex;
  flex-direction: column;
  transition: all var(--dur-fast);
  min-height: 130px;
  overflow: hidden;
}
.quick-entry:hover {
  border-color: var(--green-deep);
  background: rgba(160, 183, 133, 0.06);
  transform: translateY(-1px);
}
.quick-entry.accent {
  border-color: rgba(160, 183, 133, 0.4);
  background: rgba(160, 183, 133, 0.05);
}
.quick-entry.accent:hover {
  border-color: var(--green);
  background: rgba(160, 183, 133, 0.10);
}
.quick-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.quick-icon {
  font-family: var(--font-mono);
  font-size: 18px;
  color: var(--green);
  line-height: 1;
}
.quick-entry.accent .quick-icon { color: var(--green-bright); }
.quick-code {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.6px;
}
.quick-title {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.quick-entry.accent .quick-title { color: var(--green-bright); }
.quick-desc {
  font-size: 11px;
  color: var(--text-3);
  line-height: 1.5;
  flex: 1;
}
.quick-arrow {
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-3);
  margin-top: 10px;
  transition: transform var(--dur-fast), color var(--dur-fast);
}
.quick-entry:hover .quick-arrow {
  color: var(--green-bright);
  transform: translateX(4px);
}

/* ── 响应式 ──────────────────────────────────────────────────── */
@media (max-width: 1200px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .robust-grid { grid-template-columns: repeat(2, 1fr); }
  .quick-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 880px) {
  .dual-grid { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 560px) {
  .kpi-grid { grid-template-columns: 1fr; }
  .robust-grid { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: 1fr; }
}
</style>
