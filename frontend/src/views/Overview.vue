<script setup lang="ts">
/**
 * M00 · 系统总览(Overview) — 国家级评审 landing page
 *
 * v6 叙事基线(参见 docs/AGENT_BRIEFING.md §4 与 docs/_craic/04_申报书_v6_rewrite_draft.md):
 *   - 三模型分工 + 双视角归因(XGB-SHAP / 基线 LSTM / Attention-LSTM)
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
    subtitle: '大陆 31 个省级行政区,不含港澳台',
    tone: 'green',
    aria: '覆盖省份 31 个,即大陆 31 个省级行政区,不含港澳台',
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
    subtitle: '严格留一省协议:31 省中仅 1 省 R² > 0',
    tone: 'risk',
    aria: 'leave-province-out 协议中位 R² 为负 16.83,31 省中仅 1 省 R² 大于 0',
  },
]

// ── 双视角归因 chip 数据 ─────────────────────────────────────────────────
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

// ── 四源数据清单 ────────────────────────────────────────────────────────
// 口径：每行只描述"这一路数据是什么、覆盖到什么程度"。
// `refining` 是**同一路数据的细化项**（不是又一路数据），所以不再用「注:」小字补丁，
// 直接做成行内 amber 标签 —— 状态的语义必须自洽，否则只能靠脚注救。
interface DataSource {
  readonly name: string
  readonly detail: string
  readonly refining?: string
}

const DATA_SOURCES: ReadonlyArray<DataSource> = [
  { name: '省级统计数据', detail: '统计年鉴 + 公报 · 31 省 × 13 年' },
  {
    name: 'MODIS 卫星遥感',
    detail: 'NDVI / LST 月度合成 · 4,836 省月（全省域均值）',
    refining: '耕地像元加权未完成 · v4 仅新增 cropland_ratio',
  },
  { name: '气象与干旱指数', detail: 'CMDC 站点观测 + SPEI-3 · 省级年度聚合' },
  {
    name: 'GIS 空间基础数据',
    detail: '行政区划矢量 · 省 / 市 / 县边界',
    refining: 'CLCD 耕地掩膜未归档 · 多年序列仅完成占比统计',
  },
]

// ── 口径与边界（集中披露）──────────────────────────────────────────────
// 这些限定原本散落在各张卡片的括注与脚注里（每被误读一次就补一句），
// 结果是首页第一屏里"限制条件"比"能力"还多。集中成一块，一条不删。
const CAVEATS: ReadonlyArray<{ label: string; text: string }> = [
  {
    label: '精度口径',
    text: 'random 8:2 的 R² = 0.907 测的是省内因子相对重要性；严格留一省协议中位 −16.83（31 省仅 1 省 > 0），跨省空间外推不成立。',
  },
  {
    label: '样本规模',
    text: '省级面板 N = 403（31 省 × 13 年 × 11 维）。规模决定了深度模型的收益上限，故采用多个原理不同的轻量模型做归因对照，而非堆叠大模型。',
  },
  {
    label: '归因口径',
    text: 'SHAP 与 Attention 是互补视角，不作一致性验证；NDVI 移除后 R² 仅变化 0.003，不表述为「核心驱动因子」。',
  },
  {
    label: '县级层口径',
    text: 'M07 的县级层只吃纯气候 16 维（已剔除播种面积/规模与省-年共享常量），LCO R² = +0.4489、时间外推 +0.3644；与省级 0.907 属两套独立口径，不可比较或相加。',
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
    title: '查看异常画像',
    desc: '31 省产量异常时空分布',
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
    desc: '模型内情景推演 < 2s',
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
  {
    code: 'M06',
    title: '知识助手',
    desc: '方法论文档检索问答',
    to: '/chat',
    icon: '✦',
    accent: false,
  },
  {
    code: 'M07',
    title: '县级风险地图',
    desc: '1,199 县气候归因明细',
    to: '/county-risk',
    icon: '▦',
    accent: false,
  },
  {
    code: 'M08',
    title: '数据整备',
    desc: '上传 → 对齐 → 质检 → 导出',
    to: '/data-lab',
    icon: '⌁',
    accent: false,
  },
  {
    code: 'M09',
    title: '科研工作台',
    desc: '模型体检 · 敏感性 · 复现包',
    to: '/research',
    icon: '◎',
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
        基于<b>三模型分工 + 双视角归因</b>(XGBoost-SHAP / 基线 LSTM / Attention-LSTM),
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

    <!-- ── 双列 grid · 01 三模型分工 + 02 数据源融合 ──────────────── -->
    <div class="dual-grid">
      <!-- 左列:01 · MODEL ROLES -->
      <article
        class="card section-card"
        role="region"
        aria-labelledby="section-complementarity"
      >
        <div class="section-head">
          <div class="num">01 · MODEL ROLES · 三模型分工</div>
          <h3 id="section-complementarity">三模型分工 + 双视角归因</h3>
          <div class="section-sub">
            XGB-SHAP / LSTM / Attention-LSTM 各司其职；只有 XGB-SHAP 与
            Attention-LSTM 提供可对照的特征排序，LSTM 只作时序基线。
          </div>
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

          <div class="model-block model-block-baseline">
            <div class="model-head">
              <span class="model-name">LSTM 基线</span>
              <span class="model-tag">时序对照 · 参与 consensus</span>
            </div>
            <p class="baseline-note">
              R² 0.886，作为时序基线参与 XGB + LSTM 共识；
              <b>不提供特征级归因</b>，因此不进入下面的 Top-3 对照。
            </p>
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
              归因对照只用 XGB-SHAP 与 Attention-LSTM 两套排名；
              Spearman <span class="mono">ρ = −0.055</span>(p=0.873),
              Top-3 仅 <b>Temp</b> 一项重合
              <span class="complement-sep">→</span>
              <b class="claim">并列呈现,不作一致性验证</b>
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
          <div class="num">02 · DATA FUSION · 数据源</div>
          <h3 id="section-fusion">四源多模态数据</h3>
          <div class="section-sub">四类异构数据已统一到「省份 × 年度」口径</div>
        </div>

        <ul class="source-list">
          <li v-for="s in DATA_SOURCES" :key="s.name" class="source-item">
            <div class="source-head-row">
              <span class="source-name">{{ s.name }}</span>
              <span class="source-status st-ok">
                {{ s.refining ? '基础层已接入' : '已就绪' }}
              </span>
            </div>
            <div class="source-detail">{{ s.detail }}</div>
            <div v-if="s.refining" class="source-refining">
              <span class="refining-tag">待补</span>{{ s.refining }}
            </div>
          </li>
        </ul>
      </article>
    </div>

    <!-- ── 03 · QUICK ACCESS · 快速入口 ────────────────────────────── -->
    <article
      class="card quick-card"
      role="region"
      aria-labelledby="section-quick"
    >
      <div class="section-head">
        <div class="num">03 · QUICK ACCESS · 快速入口</div>
        <h3 id="section-quick">九大业务模块 · 一键直达</h3>
        <div class="section-sub">省级归因 → 县级归因 → 情景推演 → 知识问答,完整业务闭环</div>
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

    <!-- ── 04 · SCOPE & LIMITS · 口径与边界 ───────────────────────── -->
    <article
      class="card caveat-card"
      role="region"
      aria-labelledby="section-caveat"
    >
      <div class="section-head">
        <div class="num">04 · SCOPE &amp; LIMITS · 口径与边界</div>
        <h3 id="section-caveat">四条必须一起读的限定</h3>
        <div class="section-sub">数字脱离口径就没有意义,所以集中列在这里,而不是散在每张卡片下面</div>
      </div>
      <dl class="caveat-list">
        <div v-for="c in CAVEATS" :key="c.label" class="caveat-item">
          <dt>{{ c.label }}</dt>
          <dd>{{ c.text }}</dd>
        </div>
      </dl>
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

/* ── 三模型分工 block ─────────────────────────────────────────── */
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
.model-block-baseline {
  background: rgba(107, 168, 181, 0.06);
  border-color: rgba(107, 168, 181, 0.28);
}
.baseline-note {
  color: var(--text-2);
  font-size: 11px;
  line-height: 1.65;
}
.baseline-note b {
  color: var(--blue-bright);
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

/* ── 四源数据清单 ─────────────────────────────────────────────── */
.source-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  list-style: none;
}
.source-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.source-item:last-child { padding-bottom: 0; border-bottom: none; }
.source-head-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
}
.source-name {
  font-size: 12.5px;
  color: var(--text);
}
.source-status {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.4px;
  font-weight: 600;
  color: var(--green-bright);
}
.source-detail {
  font-size: 11px;
  color: var(--text-3);
}
.source-refining {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-2);
  margin-top: 2px;
}
.refining-tag {
  font-size: 10px;
  color: var(--amber-bright);
  border: 1px solid rgba(230, 182, 85, 0.35);
  border-radius: var(--r-sm);
  padding: 0 5px;
  flex-shrink: 0;
}

/* ── 快速入口 / 口径与边界 ─────────────────────────────────────── */
.quick-card { margin-bottom: 20px; }
.caveat-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 24px;
}
.caveat-item {
  padding-left: 12px;
  border-left: 2px solid var(--border-strong);
}
.caveat-item dt {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.4px;
  color: var(--green-bright);
  margin-bottom: 4px;
}
.caveat-item dd {
  font-size: 11.5px;
  color: var(--text-2);
  line-height: 1.65;
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
  .quick-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 880px) {
  .dual-grid { grid-template-columns: 1fr; }
  .caveat-list { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 560px) {
  .kpi-grid { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: 1fr; }
}
</style>
