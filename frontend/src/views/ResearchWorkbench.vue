<script setup lang="ts">
/**
 * M09 · 科研工作台
 *
 * 不是再做一个预测页，而是把研究过程最容易出错的四关摊开：
 * 数据口径 → 模型体检 → 情景敏感性 → 复核材料。
 * 所有数字来自 /api/research/audit 与离线模型卡；敏感性接口只做
 * XGBoost 单因素扰动，界面必须持续提示“统计关联，不是因果结论”。
 */
import { computed, onMounted, ref } from 'vue'
import { PROVINCES_BASE } from '@/data/mockProvinces'
import {
  fetchResearchAudit,
  modelCardUrl,
  postSensitivity,
  reproBundleUrl,
  type ResearchAudit,
  type SensitivityCurve,
  type SensitivityResult,
} from '@/api/research'

const audit = ref<ResearchAudit | null>(null)
const loading = ref(true)
const error = ref('')

const province = ref('河南')
const sensitivity = ref<SensitivityResult | null>(null)
const sensitivityLoading = ref(false)
const sensitivityError = ref('')

// 后端省级模型只覆盖大陆 31 省；台湾不在训练白名单，不能放进敏感性下拉。
const provinces = PROVINCES_BASE.filter((p) => p.name !== '台湾').map((p) => p.name)
const highFlags = computed(
  () => audit.value?.flags.filter((f) => f.level === 'high').length ?? 0,
)

async function loadAudit() {
  loading.value = true
  error.value = ''
  try {
    audit.value = await fetchResearchAudit()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '科研体检数据加载失败'
  } finally {
    loading.value = false
  }
}

async function runSensitivity() {
  sensitivityLoading.value = true
  sensitivityError.value = ''
  try {
    sensitivity.value = await postSensitivity(province.value)
  } catch (e) {
    sensitivityError.value = e instanceof Error ? e.message : '敏感性分析失败'
  } finally {
    sensitivityLoading.value = false
  }
}

function fmt(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

function fmtP(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  if (value < 0.001) return '< 0.001'
  return value.toFixed(3)
}

function barPct(curve: SensitivityCurve, delta: number) {
  const max = Math.max(...curve.points.map((p) => Math.abs(p.delta_risk)), 1e-9)
  return 8 + 92 * (Math.abs(delta) / max)
}

function openReproBundle() {
  window.open(reproBundleUrl(), '_blank')
}

onMounted(loadAudit)
</script>

<template>
  <section class="page">
    <header class="hero">
      <div>
        <div class="eyebrow">M09 · RESEARCH WORKBENCH</div>
        <h2>科研工作台</h2>
        <p class="lead">
          把结论送进论文之前，先过四关：数据口径、模型体检、情景敏感性、复核材料。
          系统不替研究者下结论，只把证据类型、失败模式和复现路径摊开。
        </p>
      </div>
      <div class="hero-actions">
        <button class="primary" type="button" @click="openReproBundle">
          下载复现包
        </button>
        <span class="boundary-chip">统计关联 · 非因果结论</span>
      </div>
    </header>

    <p v-if="error" class="alert" role="alert">{{ error }}</p>
    <p v-else-if="loading" class="loading" role="status">正在汇总模型卡与验证产物…</p>

    <template v-if="audit">
      <div class="gate-grid">
        <article class="gate">
          <span class="gate-no">01</span>
          <h3>数据关</h3>
          <p>{{ audit.data.panel }} · {{ audit.data.rows }} 行 · {{ audit.data.provinces }} 个截面单位</p>
          <em>{{ audit.data.note }}</em>
        </article>
        <article class="gate">
          <span class="gate-no">02</span>
          <h3>体检关</h3>
          <p>随机 / 留年 / 留省 / 分层四协议 + ICC 方差分解</p>
          <em>{{ highFlags }} 条高优先级 flag 需要先处理</em>
        </article>
        <article class="gate">
          <span class="gate-no">03</span>
          <h3>情景关</h3>
          <p>围绕本省基线做单因素扰动，输出响应曲线与排序</p>
          <em>模型内情景，不是政策效果或产量预报</em>
        </article>
        <article class="gate">
          <span class="gate-no">04</span>
          <h3>复核关</h3>
          <p>{{ audit.cards.length }} 份模型卡 + 数据哈希 + 环境版本</p>
          <em>一键导出 zip，供论文自查与审稿复核</em>
        </article>
      </div>

      <div class="split">
        <article class="card">
          <div class="card-head">
            <div>
              <span class="num">M09-A</span>
              <h3>多协议体检</h3>
            </div>
            <span class="pill">{{ audit.version }}</span>
          </div>
          <table class="protocol-table">
            <thead>
              <tr>
                <th>协议</th>
                <th>R²</th>
                <th>折数</th>
                <th>读法</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in audit.protocols" :key="p.id" :class="{ danger: p.id === 'leave_province_out' }">
                <td>{{ p.label }}</td>
                <td class="mono">
                  {{ fmt(p.r2, 3) }}
                  <small v-if="p.sd">± {{ fmt(p.sd, 3) }}</small>
                </td>
                <td class="mono">{{ p.folds }}</td>
                <td>{{ p.reads }}</td>
              </tr>
            </tbody>
          </table>
          <p class="source">来源：{{ audit.protocols[0]?.source }}</p>
        </article>

        <article class="card">
          <div class="card-head">
            <div>
              <span class="num">M09-B</span>
              <h3>方差分解</h3>
            </div>
            <span class="pill">MixedLM</span>
          </div>
          <div class="metric-row">
            <div>
              <span class="metric-label">ICC</span>
              <strong>{{ fmt(audit.variance.icc, 4) }}</strong>
              <small>95% CI [{{ fmt(audit.variance.icc_ci[0], 3) }}, {{ fmt(audit.variance.icc_ci[1], 3) }}]</small>
            </div>
            <div>
              <span class="metric-label">LRT</span>
              <strong>{{ fmt(audit.variance.lrt, 2) }}</strong>
              <small>p {{ fmtP(audit.variance.p_value_chibar) }}</small>
            </div>
          </div>
          <p class="read">{{ audit.variance.reads }}</p>
          <p class="source">来源：{{ audit.variance.source }}</p>
        </article>
      </div>

      <div class="split">
        <article class="card">
          <div class="card-head">
            <div>
              <span class="num">M09-C</span>
              <h3>双视角归因对照</h3>
            </div>
            <span class="pill">ρ = {{ fmt(audit.attribution.spearman, 3) }}</span>
          </div>
          <div class="top3-row">
            <div>
              <span class="metric-label">XGB Top-3</span>
              <div class="chips">
                <span v-for="f in audit.attribution.xgb_top3" :key="f">{{ f }}</span>
              </div>
            </div>
            <div>
              <span class="metric-label">Attention Top-3</span>
              <div class="chips alt">
                <span v-for="f in audit.attribution.att_top3" :key="f">{{ f }}</span>
              </div>
            </div>
          </div>
          <p class="read">
            Top-3 重合 {{ audit.attribution.top3_overlap }}，Top-5 重合 {{ audit.attribution.top5_overlap }}。
            {{ audit.attribution.reads }}
          </p>
          <p class="source">来源：{{ audit.attribution.source }}</p>
        </article>

        <article class="card">
          <div class="card-head">
            <div>
              <span class="num">M09-D</span>
              <h3>尺度与消融</h3>
            </div>
            <span class="pill">诊断线索</span>
          </div>
          <ul class="scale-list">
            <li>
              <b>总产方差</b>
              <span>{{ (audit.scale.log_total_variance_explained_by_area * 100).toFixed(0) }}% 由播种面积解释</span>
            </li>
            <li>
              <b>县级 LCO</b>
              <span>CLIMG 总产 {{ fmt(audit.scale.climg_lco_r2, 4) }} · 单产 {{ fmt(audit.scale.single_yield_lco_r2, 4) }}</span>
            </li>
            <li v-for="a in audit.ablations" :key="a.id">
              <b>{{ a.label }}</b>
              <span>{{ a.reads }}</span>
            </li>
          </ul>
          <p class="source">{{ audit.scale.reads }}</p>
        </article>
      </div>

      <article class="card flags-card">
        <div class="card-head">
          <div>
            <span class="num">M09-E</span>
            <h3>体检结论与下一步假设</h3>
          </div>
          <span class="pill warn">{{ highFlags }} high</span>
        </div>
        <p class="headline">{{ audit.headline }}</p>
        <div class="flag-grid">
          <section v-for="flag in audit.flags" :key="flag.title" class="flag" :class="flag.level">
            <div class="flag-head">
              <strong>{{ flag.title }}</strong>
              <span>{{ flag.level.toUpperCase() }}</span>
            </div>
            <p><b>证据</b>{{ flag.evidence }}</p>
            <p><b>含义</b>{{ flag.meaning }}</p>
            <p><b>下一步</b>{{ flag.next }}</p>
          </section>
        </div>
      </article>

      <article class="card">
        <div class="card-head">
          <div>
            <span class="num">M09-F</span>
            <h3>单因素敏感性</h3>
          </div>
          <span class="pill">XGBoost · one-at-a-time</span>
        </div>
        <div class="sensitivity-controls">
          <label for="sens-province">目标省份</label>
          <select id="sens-province" v-model="province">
            <option v-for="name in provinces" :key="name" :value="name">{{ name }}</option>
          </select>
          <button class="primary" type="button" :disabled="sensitivityLoading" @click="runSensitivity">
            {{ sensitivityLoading ? '计算中…' : '运行敏感性' }}
          </button>
        </div>
        <p v-if="sensitivityError" class="alert" role="alert">{{ sensitivityError }}</p>
        <template v-if="sensitivity">
          <p class="read">
            基线：单产 {{ fmt(sensitivity.baseline_yield_kg_per_ha, 1) }} kg/ha，
            展示风险指数 {{ fmt(sensitivity.baseline_risk, 4) }}。
            {{ sensitivity.note }}
          </p>
          <div class="curves">
            <div v-for="curve in sensitivity.curves" :key="curve.feature" class="curve">
              <div class="curve-head">
                <b>{{ curve.label }}</b>
                <span class="mono">
                  扫描 {{ fmt(curve.scan_range[0], 1) }}–{{ fmt(curve.scan_range[1], 1) }}{{ curve.unit }}
                  · 摆幅 {{ fmt(curve.swing, 4) }}
                </span>
              </div>
              <div class="spark" role="img" :aria-label="`${curve.label} 敏感性响应曲线`">
                <span
                  v-for="(point, i) in curve.points"
                  :key="i"
                  class="spark-bar"
                  :class="{ up: point.delta_risk > 0, down: point.delta_risk < 0 }"
                  :style="{ height: `${barPct(curve, point.delta_risk)}%` }"
                  :title="`${point.x}${curve.unit} → 单产 ${point.yield_kg_per_ha} kg/ha`"
                ></span>
              </div>
              <div class="curve-foot">
                <span>低端 {{ curve.points[0]?.yield_kg_per_ha ?? '—' }} kg/ha</span>
                <span>高端 {{ curve.points[curve.points.length - 1]?.yield_kg_per_ha ?? '—' }} kg/ha</span>
              </div>
            </div>
          </div>
        </template>
      </article>

      <article class="card">
        <div class="card-head">
          <div>
            <span class="num">M09-G</span>
            <h3>模型卡与复现材料</h3>
          </div>
          <button class="ghost" type="button" @click="openReproBundle">下载 zip</button>
        </div>
        <p class="read">
          模型卡记录数据版本、特征顺序、超参数、随机种子、评价协议与已知失败模式。
          复现包还包含数据 SHA-256、环境版本和结构化体检摘要。
        </p>
        <div class="card-list">
          <a
            v-for="card in audit.cards"
            :key="card.slug"
            class="model-card"
            :href="modelCardUrl(card.slug)"
            target="_blank"
            rel="noopener"
          >
            <strong>{{ card.title }}</strong>
            <span>{{ card.filename }} · {{ card.updated }}</span>
          </a>
        </div>
      </article>

      <div class="boundary">
        <strong>系统边界</strong>
        <span>{{ audit.boundary }}</span>
      </div>
    </template>
  </section>
</template>

<style scoped>
.page {
  max-width: 1260px;
  margin: 0 auto;
  padding: 28px 32px 64px;
}
.hero {
  display: flex;
  justify-content: space-between;
  gap: 28px;
  align-items: flex-start;
  margin-bottom: 22px;
}
.eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.4px;
  color: var(--green);
}
h2 {
  font-family: var(--font-serif);
  font-size: 28px;
  margin: 6px 0 8px;
}
.lead {
  max-width: 780px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.75;
}
.hero-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.boundary-chip,
.pill {
  font-family: var(--font-mono);
  font-size: 10px;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  padding: 4px 9px;
  color: var(--text-2);
}
.boundary-chip {
  color: var(--amber-bright);
  border-color: rgba(230, 182, 85, 0.35);
}
.gate-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.gate {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 16px;
}
.gate-no {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--green);
}
.gate h3 {
  font-family: var(--font-serif);
  margin: 7px 0 6px;
}
.gate p {
  color: var(--text);
  font-size: 12px;
  line-height: 1.6;
}
.gate em {
  display: block;
  margin-top: 8px;
  color: var(--text-3);
  font-size: 11px;
  font-style: normal;
  line-height: 1.5;
}
.split {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  gap: 14px;
  margin-bottom: 14px;
}
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 18px;
  margin-bottom: 14px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
  margin-bottom: 14px;
}
.num {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1px;
}
.card h3 {
  font-family: var(--font-serif);
  font-size: 16px;
  margin-top: 3px;
}
.protocol-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.protocol-table th,
.protocol-table td {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.protocol-table th {
  color: var(--text-3);
  font-weight: 500;
  font-size: 10px;
}
.protocol-table td:last-child {
  color: var(--text-2);
  line-height: 1.5;
}
.protocol-table tr.danger td:first-child,
.protocol-table tr.danger td:nth-child(2) {
  color: var(--red-bright);
}
.mono {
  font-family: var(--font-mono);
}
.protocol-table small {
  display: block;
  color: var(--text-3);
  font-size: 9px;
}
.metric-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.metric-label {
  display: block;
  color: var(--text-3);
  font-size: 10px;
  font-family: var(--font-mono);
  margin-bottom: 5px;
}
.metric-row strong {
  display: block;
  color: var(--green-bright);
  font-family: var(--font-mono);
  font-size: 24px;
}
.metric-row small {
  color: var(--text-3);
  font-size: 10px;
}
.read {
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.7;
  margin-top: 12px;
}
.source {
  color: var(--text-3);
  font-size: 10px;
  margin-top: 10px;
}
.top3-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chips span {
  border: 1px solid rgba(160, 183, 133, 0.35);
  background: rgba(160, 183, 133, 0.08);
  border-radius: var(--r-md);
  padding: 4px 7px;
  font-family: var(--font-mono);
  font-size: 10px;
}
.chips.alt span {
  border-color: rgba(230, 182, 85, 0.35);
  background: rgba(230, 182, 85, 0.08);
}
.scale-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.scale-list li {
  display: flex;
  gap: 10px;
  font-size: 11px;
  line-height: 1.55;
}
.scale-list b {
  min-width: 82px;
  color: var(--text);
}
.scale-list span {
  color: var(--text-2);
}
.headline {
  color: var(--green-bright);
  font-size: 12px;
  line-height: 1.7;
  margin-bottom: 14px;
}
.flag-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.flag {
  border: 1px solid var(--border);
  border-left: 3px solid var(--amber);
  border-radius: var(--r-md);
  padding: 12px;
  background: var(--bg-2);
}
.flag.high {
  border-left-color: var(--red-bright);
}
.flag.medium {
  border-left-color: var(--amber);
}
.flag-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.flag-head strong {
  font-size: 12px;
}
.flag-head span {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
}
.flag p {
  color: var(--text-2);
  font-size: 11px;
  line-height: 1.55;
  margin-top: 4px;
}
.flag p b {
  color: var(--text);
  margin-right: 5px;
}
.sensitivity-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.sensitivity-controls label {
  color: var(--text-3);
  font-size: 11px;
}
select {
  background: var(--bg-2);
  border: 1px solid var(--border-strong);
  color: var(--text);
  border-radius: var(--r-md);
  padding: 7px 10px;
}
.primary,
.ghost {
  border-radius: var(--r-md);
  padding: 8px 13px;
  font-size: 11px;
  cursor: pointer;
}
.primary {
  background: var(--green-deep);
  color: #0E1A14;
  border: 1px solid var(--green);
  font-weight: 600;
}
.ghost {
  background: transparent;
  color: var(--text-2);
  border: 1px solid var(--border-strong);
}
.primary:disabled {
  opacity: 0.55;
  cursor: wait;
}
.curves {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 14px;
}
.curve {
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 11px 12px;
  background: var(--bg-2);
}
.curve-head,
.curve-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 10px;
  color: var(--text-2);
}
.curve-head b {
  font-size: 12px;
  color: var(--text);
}
.spark {
  height: 48px;
  display: flex;
  align-items: flex-end;
  gap: 3px;
  margin: 8px 0 4px;
}
.spark-bar {
  flex: 1;
  min-height: 2px;
  border-radius: 2px 2px 0 0;
  background: var(--green);
  opacity: 0.8;
}
.spark-bar.up {
  background: var(--red-bright);
}
.spark-bar.down {
  background: var(--green-bright);
}
.card-list {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.model-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 11px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--bg-2);
  transition: border-color var(--dur-fast);
}
.model-card:hover {
  border-color: var(--green);
}
.model-card strong {
  font-size: 11px;
  color: var(--text);
}
.model-card span {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
}
.boundary {
  display: flex;
  gap: 14px;
  border: 1px dashed rgba(230, 182, 85, 0.4);
  background: rgba(230, 182, 85, 0.06);
  border-radius: var(--r-lg);
  padding: 14px 16px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-2);
}
.boundary strong {
  color: var(--amber-bright);
  flex-shrink: 0;
}
.alert {
  background: rgba(184, 111, 77, 0.12);
  border: 1px solid rgba(184, 111, 77, 0.35);
  border-radius: var(--r-md);
  padding: 10px 12px;
  color: var(--red-bright);
  font-size: 12px;
}
.loading {
  color: var(--text-2);
  font-size: 12px;
}
@media (max-width: 980px) {
  .gate-grid,
  .split,
  .flag-grid,
  .card-list {
    grid-template-columns: 1fr;
  }
  .hero {
    flex-direction: column;
  }
  .hero-actions {
    align-items: flex-start;
  }
}
</style>
