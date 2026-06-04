<script setup lang="ts">
/**
 * M05 · 推演监控面板
 *
 * 实时追踪三模型(XGBoost / LSTM / Attention-LSTM)对每次省份风险查询的协同推演过程。
 *
 * 数据源:GET /api/admin/predicts(每 3s 轮询一次)
 * 当 M02 / M03 / M04 触发 /api/predict 时,trace 会自动出现在此面板。
 *
 * 视觉风格沿用 M01-M04 的 .page / .card / .eyebrow / .lead 体系,
 * 不暴露任何后端实现细节(ring buffer / polling 周期 / endpoint 路径等)。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchPredictHistory, type PredictTrace } from '@/api/admin'

// 11 维特征中英映射,用于参数展开 panel
const FEATURE_LABELS: Record<string, string> = {
  irr: '灌溉率',
  flood: '洪涝占比',
  sun: '日照时数',
  temp: '平均气温',
  spei: 'SPEI 干旱指数',
  prec: '降水量',
  mech: '农机总动力',
  fert: '化肥施用量',
  drou_a: '旱灾面积',
  flood_a: '水灾面积',
  ndvi: 'NDVI 异常',
}

const MODEL_LABELS: Record<string, string> = {
  xgboost: 'XGBoost',
  lstm: 'LSTM',
  ensemble: '三模型协同',
}

// ── 状态 ────────────────────────────────────────────────────────────────────
const traces = ref<PredictTrace[]>([])
const totalCount = ref(0)
const maxCapacity = ref(50)
const isLoading = ref(true)
const fetchError = ref<string | null>(null)
const expandedTs = ref<string | null>(null)   // 展开的行 (用 ts 唯一标识)
const lastUpdated = ref<Date | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null

// ── Polling ────────────────────────────────────────────────────────────────
async function refresh() {
  try {
    const data = await fetchPredictHistory()
    traces.value = data.items
    totalCount.value = data.count
    maxCapacity.value = data.max
    fetchError.value = null
    lastUpdated.value = new Date()
  } catch (e: unknown) {
    fetchError.value = e instanceof Error ? e.message : '网络异常'
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  refresh()
  // 每 3 秒刷新一次
  pollTimer = setInterval(refresh, 3000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// ── 派生数据 ────────────────────────────────────────────────────────────────

/** 平均 latency (ms),保留 1 位小数 */
const avgLatency = computed(() => {
  if (traces.value.length === 0) return null
  const sum = traces.value.reduce((s, t) => s + (t.latency_ms || 0), 0)
  return +(sum / traces.value.length).toFixed(1)
})

/** 模型平均 risk(在 ensemble trace 中提取) */
function avgRisk(field: keyof PredictTrace): number | null {
  const vals = traces.value
    .map((t) => t[field])
    .filter((v): v is number => typeof v === 'number')
  if (vals.length === 0) return null
  return +(vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(4)
}

const avgXgb = computed(() => avgRisk('xgboost_risk'))
const avgLstm = computed(() => avgRisk('lstm_risk'))
const avgAtt = computed(() => avgRisk('att_lstm_risk'))
const avgConsensus = computed(() => avgRisk('consensus'))

/** 三模型协同调用占比 */
const ensembleRatio = computed(() => {
  if (traces.value.length === 0) return null
  const n = traces.value.filter((t) => t.model === 'ensemble').length
  return Math.round((n / traces.value.length) * 100)
})

/** divergence 分布:转成 8 桶 sparkline,用于显示三模型分歧形态 */
const divergenceBars = computed<number[]>(() => {
  const ensembles = traces.value.filter(
    (t) => typeof t.divergence === 'number',
  ) as Array<PredictTrace & { divergence: number }>
  if (ensembles.length === 0) return []
  // 把 divergence 投到 [0, max] 区间,分 8 桶统计
  const max = Math.max(...ensembles.map((t) => t.divergence), 0.001)
  const bins = new Array(8).fill(0) as number[]
  for (const t of ensembles) {
    const idx = Math.min(7, Math.floor((t.divergence / max) * 8))
    bins[idx] += 1
  }
  const maxBin = Math.max(...bins, 1)
  return bins.map((c) => c / maxBin)
})

const divergenceTooltip = computed(() => {
  const ensembles = traces.value.filter((t) => typeof t.divergence === 'number')
  if (ensembles.length === 0) return '尚无三模型协同数据'
  const max = Math.max(...ensembles.map((t) => t.divergence || 0))
  return `${ensembles.length} 次三模型调用 · 最大分歧 ${max.toFixed(4)}`
})

// ── 表格行交互 ──────────────────────────────────────────────────────────────
function toggleRow(ts: string) {
  expandedTs.value = expandedTs.value === ts ? null : ts
}

// ── 格式化工具 ──────────────────────────────────────────────────────────────
function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  // HH:MM:SS,本地时区
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

function fmtRisk(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(4)
}

function fmtYield(v: number | null | undefined): string {
  if (v == null) return '—'
  return Math.round(v).toString()
}

function fmtDelta(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(4)}`
}

/** 风险数值 → 色阶 class(与 M01 一致的赭石→琥珀→绿) */
function riskClass(risk: number): string {
  if (risk >= 0.040) return 'risk-vh'
  if (risk >= 0.030) return 'risk-h'
  if (risk >= 0.024) return 'risk-m'
  if (risk >= 0.020) return 'risk-l'
  return 'risk-vl'
}

/** divergence 数值 → 提示文案 + class */
function divergenceClass(d: number | null | undefined): string {
  if (d == null) return ''
  if (d >= 0.005) return 'div-h'
  if (d >= 0.002) return 'div-m'
  return 'div-l'
}

/** SHAP top 列表里的最大绝对值,用作进度条归一化 */
function shapMax(items: { value: number }[]): number {
  if (items.length === 0) return 1
  return Math.max(...items.map((i) => Math.abs(i.value)), 0.001)
}

/** 与该省 baseline 的相对偏差(单位 %) */
function yieldDeviation(modelYield: number | null | undefined, baselineRisk: number): string {
  if (modelYield == null) return '—'
  // baseline 是 risk,我们没有 baseline_yield;用 modelYield 自身相对中位风险 0.0235 反推近似
  // 这里做最简单的展示:若 _BASELINE_RISK = 0.0235,我们直接展示 yield 数值
  // 把 baselineRisk 信息留作上下文,不强行换算
  void baselineRisk
  return `${Math.round(modelYield)} kg/ha`
}
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M05 · INFERENCE TRACE</div>
      <h2>推演监控</h2>
      <p class="lead">
        实时追踪三模型(XGBoost / LSTM / Attention-LSTM)对每次省份风险查询的协同推演过程。
        每行展开后可查看 11 维输入参数、三模型独立输出与归因因子。
      </p>
    </header>

    <!-- 顶部统计卡 -->
    <div class="stat-grid" role="region" aria-label="推演汇总指标">
      <div class="stat-card">
        <div class="num">M05-0 · TOTAL</div>
        <div class="stat-value">{{ totalCount }}</div>
        <div class="stat-label">累计调用</div>
        <div class="stat-sub">窗口容量 {{ maxCapacity }}</div>
      </div>

      <div class="stat-card">
        <div class="num">M05-1 · LATENCY</div>
        <div class="stat-value">
          <template v-if="avgLatency != null">
            {{ avgLatency }}<span class="unit">ms</span>
          </template>
          <template v-else>—</template>
        </div>
        <div class="stat-label">单次平均响应</div>
        <div class="stat-sub">含三模型并行推理</div>
      </div>

      <div class="stat-card">
        <div class="num">M05-2 · XGBOOST</div>
        <div class="stat-value">{{ fmtRisk(avgXgb) }}</div>
        <div class="stat-label">XGBoost 平均 risk</div>
        <div class="stat-sub">树模型 · 表征非线性结构</div>
      </div>

      <div class="stat-card">
        <div class="num">M05-3 · LSTM</div>
        <div class="stat-value">{{ fmtRisk(avgLstm) }}</div>
        <div class="stat-label">LSTM 平均 risk</div>
        <div class="stat-sub">序列模型 · 表征时序依赖</div>
      </div>

      <div class="stat-card">
        <div class="num">M05-4 · ATT-LSTM</div>
        <div class="stat-value">{{ fmtRisk(avgAtt) }}</div>
        <div class="stat-label">Attention-LSTM 平均 risk</div>
        <div class="stat-sub">注意力加权 · 关键期高亮</div>
      </div>

      <div class="stat-card">
        <div class="num">M05-5 · CONSENSUS</div>
        <div class="stat-value">{{ fmtRisk(avgConsensus) }}</div>
        <div class="stat-label">三模型共识 risk</div>
        <div class="stat-sub">
          <span v-if="ensembleRatio != null">{{ ensembleRatio }}% 调用为三模型协同</span>
          <span v-else>尚无协同调用</span>
        </div>
      </div>

      <div class="stat-card stat-card-wide">
        <div class="num">M05-6 · DIVERGENCE</div>
        <div class="diverge-row">
          <div class="diverge-bars" :title="divergenceTooltip" :aria-label="divergenceTooltip">
            <span
              v-for="(h, i) in divergenceBars"
              :key="i"
              class="diverge-bar"
              :style="{ height: `${Math.max(8, h * 100)}%` }"
            />
            <span v-if="divergenceBars.length === 0" class="diverge-empty">尚无数据</span>
          </div>
          <div class="diverge-meta">
            <div class="stat-label">三模型分歧分布</div>
            <div class="stat-sub">XGBoost ↔ LSTM 风险差异</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Trace 列表 -->
    <div class="card trace-card">
      <div class="card-head">
        <div>
          <div class="num">M05-T · RECENT CALLS</div>
          <h3>近期推演调用</h3>
        </div>
        <div class="head-right">
          <span v-if="lastUpdated" class="updated">
            最新刷新 {{ lastUpdated.toLocaleTimeString('zh-CN', { hour12: false }) }}
          </span>
          <span v-if="fetchError" class="err-chip">{{ fetchError }}</span>
        </div>
      </div>

      <!-- 表头 -->
      <div class="trace-table" role="table" aria-label="近期推演调用列表">
        <div class="trace-row trace-head" role="row">
          <div class="col col-time" role="columnheader">时间</div>
          <div class="col col-prov" role="columnheader">省份</div>
          <div class="col col-model" role="columnheader">模型</div>
          <div class="col col-risk" role="columnheader">风险 risk</div>
          <div class="col col-cons" role="columnheader">共识</div>
          <div class="col col-div" role="columnheader">分歧</div>
          <div class="col col-lat" role="columnheader">响应</div>
          <div class="col col-toggle" role="columnheader" aria-hidden="true"></div>
        </div>

        <!-- 空状态 -->
        <div v-if="isLoading && traces.length === 0" class="empty">
          <div class="spinner" aria-hidden="true"></div>
          <div>正在拉取推演记录…</div>
        </div>
        <div v-else-if="!isLoading && traces.length === 0" class="empty">
          <div class="empty-icon" aria-hidden="true">∅</div>
          <div>尚无推演记录</div>
          <div class="empty-hint">在 M02 / M03 / M04 触发模型预测即可看到</div>
        </div>

        <!-- 数据行 -->
        <template v-for="t in traces" :key="t.ts">
          <div
            class="trace-row"
            role="row"
            :class="{ expanded: expandedTs === t.ts }"
            tabindex="0"
            :aria-expanded="expandedTs === t.ts"
            @click="toggleRow(t.ts)"
            @keydown.enter.prevent="toggleRow(t.ts)"
            @keydown.space.prevent="toggleRow(t.ts)"
          >
            <div class="col col-time" role="cell">{{ fmtTime(t.ts) }}</div>
            <div class="col col-prov" role="cell">{{ t.province }}</div>
            <div class="col col-model" role="cell">
              <span class="model-chip" :class="`mc-${t.model}`">
                {{ MODEL_LABELS[t.model] || t.model }}
              </span>
            </div>
            <div class="col col-risk" role="cell">
              <span class="risk-pill" :class="riskClass(t.risk_score)">
                {{ fmtRisk(t.risk_score) }}
              </span>
            </div>
            <div class="col col-cons" role="cell">{{ fmtRisk(t.consensus) }}</div>
            <div class="col col-div" role="cell">
              <span :class="divergenceClass(t.divergence)">{{ fmtRisk(t.divergence) }}</span>
            </div>
            <div class="col col-lat" role="cell">{{ t.latency_ms }} ms</div>
            <div class="col col-toggle" role="cell" aria-hidden="true">
              <span class="caret" :class="{ open: expandedTs === t.ts }">›</span>
            </div>
          </div>

          <!-- 展开 detail panel -->
          <div v-if="expandedTs === t.ts" class="trace-detail" role="region" :aria-label="`${t.province} 推演详情`">
            <!-- 三模型独立输出 -->
            <div class="detail-section">
              <div class="section-title">三模型推演输出</div>
              <div class="model-grid">
                <div class="model-card" :class="{ active: t.model === 'xgboost' || t.model === 'ensemble' }">
                  <div class="mc-name">XGBoost</div>
                  <div class="mc-yield">
                    {{ fmtYield(t.xgboost_yield_kg_per_ha ?? (t.model === 'xgboost' ? t.yield_kg_per_ha : null)) }}
                    <span class="mc-unit">kg/ha</span>
                  </div>
                  <div class="mc-risk-row">
                    <span class="mc-label">→ risk</span>
                    <span class="mc-risk" :class="riskClass(t.xgboost_risk ?? (t.model === 'xgboost' ? t.risk_score : 0))">
                      {{ fmtRisk(t.xgboost_risk ?? (t.model === 'xgboost' ? t.risk_score : null)) }}
                    </span>
                  </div>
                  <div class="mc-desc">梯度提升树 · 非线性特征交互</div>
                </div>

                <div class="model-card" :class="{ active: t.model === 'lstm' || t.model === 'ensemble' }">
                  <div class="mc-name">LSTM</div>
                  <div class="mc-yield">
                    {{ fmtYield(t.lstm_yield_kg_per_ha ?? (t.model === 'lstm' ? t.yield_kg_per_ha : null)) }}
                    <span class="mc-unit">kg/ha</span>
                  </div>
                  <div class="mc-risk-row">
                    <span class="mc-label">→ risk</span>
                    <span class="mc-risk" :class="riskClass(t.lstm_risk ?? (t.model === 'lstm' ? t.risk_score : 0))">
                      {{ fmtRisk(t.lstm_risk ?? (t.model === 'lstm' ? t.risk_score : null)) }}
                    </span>
                  </div>
                  <div class="mc-desc">长短期记忆 · 序列时序依赖</div>
                </div>

                <div class="model-card" :class="{ active: t.model === 'ensemble' }">
                  <div class="mc-name">Attention-LSTM</div>
                  <div class="mc-yield">
                    {{ fmtYield(t.att_lstm_yield_kg_per_ha) }}
                    <span class="mc-unit">kg/ha</span>
                  </div>
                  <div class="mc-risk-row">
                    <span class="mc-label">→ risk</span>
                    <span class="mc-risk" :class="riskClass(t.att_lstm_risk ?? 0)">
                      {{ fmtRisk(t.att_lstm_risk) }}
                    </span>
                  </div>
                  <div class="mc-desc">注意力加权 · 关键时段聚焦</div>
                </div>
              </div>
              <div class="consensus-line" v-if="t.model === 'ensemble'">
                <span class="cl-label">共识 risk</span>
                <span class="cl-val">{{ fmtRisk(t.consensus) }}</span>
                <span class="cl-sep">·</span>
                <span class="cl-label">三模型分歧</span>
                <span class="cl-val" :class="divergenceClass(t.divergence)">{{ fmtRisk(t.divergence) }}</span>
                <span class="cl-sep">·</span>
                <span class="cl-label">基线偏离</span>
                <span class="cl-val">{{ fmtDelta(t.delta) }}</span>
              </div>
            </div>

            <!-- 输入 11 维 -->
            <div class="detail-section">
              <div class="section-title">
                输入参数
                <span v-if="t.params_filled_from_baseline.length > 0" class="title-hint">
                  {{ t.params_filled_from_baseline.length }} 项由历史基线补全
                </span>
              </div>
              <div class="params-grid">
                <div
                  v-for="(label, key) in FEATURE_LABELS"
                  :key="key"
                  class="param-cell"
                  :class="{ filled: t.params_filled_from_baseline.includes(String(key)) }"
                >
                  <div class="param-key">{{ label }}</div>
                  <div class="param-val">{{ t.params[String(key)]?.toFixed(2) ?? '—' }}</div>
                  <div v-if="t.params_filled_from_baseline.includes(String(key))" class="param-tag">
                    基线
                  </div>
                </div>
              </div>
            </div>

            <!-- SHAP top -->
            <div v-if="t.shap_top.length > 0" class="detail-section">
              <div class="section-title">关键因子归因(SHAP Top 5)</div>
              <div class="shap-list">
                <div
                  v-for="s in t.shap_top"
                  :key="s.feature"
                  class="shap-row"
                  :class="s.direction"
                >
                  <div class="shap-name">{{ s.feature }}</div>
                  <div class="shap-track">
                    <div
                      class="shap-bar"
                      :class="s.direction"
                      :style="{ width: `${(Math.abs(s.value) / shapMax(t.shap_top)) * 100}%` }"
                    ></div>
                  </div>
                  <div class="shap-val">
                    {{ s.value > 0 ? '+' : '' }}{{ s.value.toFixed(4) }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Recommendations -->
            <div v-if="t.recommendations.length > 0" class="detail-section">
              <div class="section-title">应对建议</div>
              <ul class="rec-list">
                <li v-for="r in t.recommendations" :key="r.factor" class="rec-item">
                  <span class="rec-priority" :class="`p-${r.priority}`">{{ r.priority }}</span>
                  <span class="rec-factor">{{ r.factor }}</span>
                  <span class="rec-arrow">→</span>
                  <span class="rec-action">{{ r.action }}</span>
                </li>
              </ul>
            </div>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1480px; margin: 0 auto; }

.page-head { margin-bottom: 20px; }
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
  font-size: 26px;
  font-weight: 600;
  margin-bottom: 6px;
}
.lead {
  font-size: 13px;
  color: var(--text-2);
  max-width: 920px;
  line-height: 1.7;
}

/* ── 顶部统计卡 ─────────────────────────────────────────────────────────── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 14px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.stat-card.stat-card-wide {
  grid-column: span 1;
}
.stat-card .num {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.stat-value {
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 600;
  color: var(--green-bright);
  line-height: 1.1;
  margin-bottom: 4px;
}
.stat-value .unit {
  font-size: 12px;
  color: var(--text-2);
  margin-left: 2px;
}
.stat-label {
  font-size: 11px;
  color: var(--text);
  margin-bottom: 2px;
}
.stat-sub {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.3px;
}

/* divergence sparkline */
.diverge-row {
  display: flex;
  align-items: stretch;
  gap: 10px;
  flex: 1;
  min-height: 0;
}
.diverge-bars {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 44px;
  flex: 1;
  padding: 4px 0;
}
.diverge-bar {
  flex: 1;
  background: linear-gradient(to top, var(--green-deep), var(--green-bright));
  border-radius: 2px;
  min-height: 4px;
  transition: height var(--dur-base) var(--ease-out);
}
.diverge-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  align-self: center;
}
.diverge-meta {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  flex-shrink: 0;
  text-align: right;
}

/* ── trace card / 表格 ─────────────────────────────────────────────────── */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-head .num {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1px;
  margin-bottom: 2px;
}
.card-head h3 {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 600;
}
.head-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.updated {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.3px;
}
.err-chip {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--red-bright);
  background: rgba(184, 111, 77, 0.12);
  border: 1px solid rgba(184, 111, 77, 0.3);
  border-radius: var(--r-sm);
  padding: 2px 8px;
}

.trace-table {
  display: flex;
  flex-direction: column;
}
.trace-row {
  display: grid;
  grid-template-columns: 90px 90px 130px 100px 90px 90px 80px 30px;
  gap: 8px;
  padding: 10px 8px;
  border-bottom: 1px solid var(--border);
  align-items: center;
  font-size: 12px;
  cursor: pointer;
  transition: background var(--dur-fast);
}
.trace-row:hover:not(.trace-head) {
  background: rgba(160, 183, 133, 0.05);
}
.trace-row.expanded {
  background: rgba(160, 183, 133, 0.07);
  border-bottom-color: var(--border-strong);
}
.trace-row.trace-head {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.6px;
  text-transform: uppercase;
  cursor: default;
  padding-top: 4px;
  padding-bottom: 8px;
}
.trace-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.col { font-family: var(--font-mono); color: var(--text); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-prov { font-family: var(--font-sans); font-weight: 500; }

.model-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.3px;
  border: 1px solid var(--border-strong);
  background: var(--bg-elev);
  color: var(--text-2);
}
.model-chip.mc-ensemble {
  border-color: rgba(160, 183, 133, 0.4);
  color: var(--green-bright);
  background: rgba(160, 183, 133, 0.08);
}
.model-chip.mc-xgboost {
  border-color: rgba(143, 193, 204, 0.35);
  color: var(--blue-bright);
}
.model-chip.mc-lstm {
  border-color: rgba(180, 157, 216, 0.35);
  color: var(--purple);
}

.risk-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--r-md);
  font-family: var(--font-mono);
  font-weight: 600;
  border: 1px solid transparent;
}
.risk-pill.risk-vh { background: rgba(126, 69, 48, 0.25); color: var(--risk-1); border-color: var(--risk-5); }
.risk-pill.risk-h  { background: rgba(165, 101, 72, 0.22); color: var(--risk-1); border-color: var(--risk-4); }
.risk-pill.risk-m  { background: rgba(230, 182, 85, 0.18); color: var(--amber-bright); border-color: var(--amber); }
.risk-pill.risk-l  { background: rgba(160, 183, 133, 0.16); color: var(--green-bright); border-color: var(--green); }
.risk-pill.risk-vl { background: rgba(160, 183, 133, 0.10); color: var(--green-bright); border-color: var(--green-deep); }

.div-h { color: var(--red-bright); }
.div-m { color: var(--amber-bright); }
.div-l { color: var(--text-2); }

.col-toggle { text-align: right; }
.caret {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-3);
  transition: transform var(--dur-fast);
}
.caret.open { transform: rotate(90deg); color: var(--green-bright); }

/* ── 空状态 ─────────────────────────────────────────────────────────────── */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 16px;
  color: var(--text-3);
  font-size: 13px;
}
.empty-icon {
  font-family: var(--font-mono);
  font-size: 32px;
  color: var(--text-3);
  opacity: 0.5;
  margin-bottom: 4px;
}
.empty-hint {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-3);
}
.spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--bg-elev);
  border-top-color: var(--green);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 展开 detail panel ─────────────────────────────────────────────────── */
.trace-detail {
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  padding: 18px 16px 22px 16px;
  margin: 0 -8px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.section-title {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 1.2px;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 10px;
}
.title-hint {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--amber);
  background: rgba(230, 182, 85, 0.1);
  border: 1px solid rgba(230, 182, 85, 0.25);
  border-radius: var(--r-sm);
  padding: 2px 7px;
  text-transform: none;
  letter-spacing: 0.3px;
}

/* 三模型卡 */
.model-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.model-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 12px 14px;
  opacity: 0.55;
  transition: opacity var(--dur-fast), border-color var(--dur-fast);
}
.model-card.active {
  opacity: 1;
  border-color: var(--border-strong);
}
.mc-name {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--green-bright);
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.mc-yield {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.1;
}
.mc-unit {
  font-size: 11px;
  color: var(--text-3);
  margin-left: 4px;
  font-weight: 400;
}
.mc-risk-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.mc-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
}
.mc-risk {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: var(--r-sm);
  border: 1px solid transparent;
}
.mc-risk.risk-vh { background: rgba(126, 69, 48, 0.25); color: var(--risk-1); border-color: var(--risk-5); }
.mc-risk.risk-h  { background: rgba(165, 101, 72, 0.22); color: var(--risk-1); border-color: var(--risk-4); }
.mc-risk.risk-m  { background: rgba(230, 182, 85, 0.18); color: var(--amber-bright); border-color: var(--amber); }
.mc-risk.risk-l  { background: rgba(160, 183, 133, 0.16); color: var(--green-bright); border-color: var(--green); }
.mc-risk.risk-vl { background: rgba(160, 183, 133, 0.10); color: var(--green-bright); border-color: var(--green-deep); }
.mc-desc {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  margin-top: 8px;
  letter-spacing: 0.3px;
}

.consensus-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
}
.consensus-line .cl-label { color: var(--text-3); }
.consensus-line .cl-val { color: var(--green-bright); font-weight: 600; }
.consensus-line .cl-sep { color: var(--border-strong); }

/* 参数 grid */
.params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}
.param-cell {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 8px 10px;
  position: relative;
}
.param-cell.filled {
  border-style: dashed;
  background: var(--bg);
  opacity: 0.78;
}
.param-key {
  font-size: 11px;
  color: var(--text-2);
  margin-bottom: 2px;
}
.param-val {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.param-tag {
  position: absolute;
  top: 4px;
  right: 4px;
  font-family: var(--font-mono);
  font-size: 8px;
  color: var(--amber);
  background: rgba(230, 182, 85, 0.1);
  border: 1px solid rgba(230, 182, 85, 0.25);
  border-radius: var(--r-sm);
  padding: 1px 4px;
  letter-spacing: 0.3px;
}

/* SHAP 列表 */
.shap-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.shap-row {
  display: grid;
  grid-template-columns: 130px 1fr 76px;
  gap: 12px;
  align-items: center;
  padding: 4px 0;
}
.shap-name { font-size: 12px; color: var(--text); }
.shap-track {
  height: 8px;
  background: var(--bg-elev);
  border-radius: 4px;
  overflow: hidden;
}
.shap-bar {
  height: 100%;
  border-radius: 4px;
  transition: width var(--dur-base) var(--ease-out);
}
.shap-bar.harm { background: linear-gradient(to right, var(--risk-5), var(--risk-3)); }
.shap-bar.protect { background: linear-gradient(to right, var(--green-deep), var(--green-bright)); }
.shap-val {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-align: right;
}
.shap-row.harm .shap-val { color: var(--risk-2); }
.shap-row.protect .shap-val { color: var(--green-bright); }

/* recommendations */
.rec-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rec-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 8px 12px;
}
.rec-priority {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: var(--r-sm);
  flex-shrink: 0;
}
.rec-priority.p-high { background: rgba(184, 111, 77, 0.18); color: var(--red-bright); border: 1px solid rgba(184, 111, 77, 0.4); }
.rec-priority.p-medium { background: rgba(230, 182, 85, 0.16); color: var(--amber-bright); border: 1px solid rgba(230, 182, 85, 0.4); }
.rec-priority.p-low { background: rgba(160, 183, 133, 0.14); color: var(--green-bright); border: 1px solid rgba(160, 183, 133, 0.4); }
.rec-factor { font-weight: 600; color: var(--green-bright); }
.rec-arrow { color: var(--text-3); font-family: var(--font-mono); }
.rec-action { color: var(--text-2); }

/* ── 响应式 ─────────────────────────────────────────────────────────────── */
@media (max-width: 1280px) {
  .stat-grid { grid-template-columns: repeat(4, 1fr); }
  .stat-card.stat-card-wide { grid-column: span 4; }
}
@media (max-width: 768px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .stat-card.stat-card-wide { grid-column: span 2; }
  .trace-row {
    grid-template-columns: 80px 70px 100px 90px 70px 30px;
  }
  .col-cons, .col-lat { display: none; }
  .model-grid { grid-template-columns: 1fr; }
}
</style>
