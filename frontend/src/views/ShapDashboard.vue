<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { getCSSVar } from '@/data/mockProvinces'

interface Feature {
  name: string
  en: string
  shap: number
  dir: 'green' | 'red'
}

const FEATURES_ALL: Feature[] = [
  { name: '灌溉率', en: 'Irr', shap: 0.420, dir: 'green' },
  { name: '洪涝占比', en: 'Flood_R', shap: 0.385, dir: 'red' },
  { name: '日照时数', en: 'Sun', shap: 0.312, dir: 'green' },
  { name: '平均气温', en: 'Temp', shap: 0.225, dir: 'red' },
  { name: '降水量', en: 'Prec', shap: 0.185, dir: 'red' },
  { name: '干旱指数', en: 'SPEI', shap: 0.162, dir: 'green' },
  { name: '农机总动力', en: 'Mech', shap: 0.124, dir: 'green' },
  { name: '化肥施用量', en: 'Fert', shap: 0.092, dir: 'red' },
  { name: '旱灾面积', en: 'Drou_A', shap: 0.075, dir: 'red' },
  { name: '水灾面积', en: 'Flood_A', shap: 0.058, dir: 'red' },
  { name: 'NDVI 异常', en: 'NDVI', shap: 0.034, dir: 'green' },
]

type SubsetKey = 'all' | 'north' | 'south' | 'major'

interface Subset {
  key: SubsetKey
  label: string
  sampleN: number
  cover: number
  mods: Record<string, number>
}

const SUBSETS: Subset[] = [
  { key: 'all', label: '全样本 (31 省)', sampleN: 403, cover: 31, mods: {} },
  { key: 'north', label: '北方 (14 省)', sampleN: 169, cover: 14, mods: { '灌溉率': 1.18, '日照时数': 1.22, '干旱指数': 1.35, '旱灾面积': 1.45, '洪涝占比': 0.55, '水灾面积': 0.42, '降水量': 0.78 } },
  { key: 'south', label: '南方 (12 省)', sampleN: 156, cover: 12, mods: { '灌溉率': 0.72, '洪涝占比': 1.32, '水灾面积': 1.55, '降水量': 1.28, '日照时数': 0.85, '干旱指数': 0.42, '旱灾面积': 0.38 } },
  { key: 'major', label: '主产区 (13 省)', sampleN: 169, cover: 13, mods: { '灌溉率': 1.08, '化肥施用量': 1.42, '农机总动力': 1.38, '洪涝占比': 1.05, '降水量': 0.92 } },
]

const subset = ref<SubsetKey>('all')
const currentSubset = computed(() => SUBSETS.find((s) => s.key === subset.value)!)

const features = computed<Feature[]>(() => {
  const mods = currentSubset.value.mods
  return FEATURES_ALL.map((f) => ({ ...f, shap: +(f.shap * (mods[f.name] || 1)).toFixed(3) })).sort(
    (a, b) => b.shap - a.shap,
  )
})

// Waterfall 河南 2022 单样本数据（与 prototype 一致）
interface WaterfallStep {
  name: string
  val?: number
  delta?: number
  type: 'baseline' | 'pos' | 'neg' | 'final'
}

const WATERFALL_STEPS: WaterfallStep[] = [
  { name: '基线 E[f(x)]', val: 0.0235, type: 'baseline' },
  { name: '洪涝 4.2%', delta: 0.0028, type: 'pos' },
  { name: '化肥施用量', delta: 0.0009, type: 'pos' },
  { name: '气温 14.2°C', delta: 0.0015, type: 'pos' },
  { name: '灌溉 65.4%', delta: -0.0022, type: 'neg' },
  { name: '日照 2240h', delta: -0.0011, type: 'neg' },
  { name: '农机总动力', delta: -0.0005, type: 'neg' },
  { name: '预测 f(x)', val: 0.0249, type: 'final' },
]

// 伪随机 beeswarm 数据生成
function seededRandom(seed: number): () => number {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

interface BeePoint {
  fi: number
  shap: number
  raw: number
  yPos: number
  rawNorm: number
}

function generateBeeswarmPoints(subsetKey: SubsetKey): { features: string[]; points: BeePoint[] } {
  const feats = [
    { name: '灌溉率', sign: -1, spread: 0.6, range: [25, 110] },
    { name: '洪涝占比', sign: 1, spread: 0.55, range: [0, 22] },
    { name: '日照时数', sign: -1, spread: 0.45, range: [1180, 3320] },
    { name: '平均气温', sign: 1, spread: 0.4, range: [3, 24] },
    { name: 'SPEI 干旱', sign: -1, spread: 0.35, range: [-2.5, 2.8] },
  ]
  const mods = currentSubset.value.mods
  const points: BeePoint[] = []
  feats.forEach((f, fi) => {
    const modKey = f.name === 'SPEI 干旱' ? '干旱指数' : f.name
    const mod = mods[modKey] || 1
    const rng = seededRandom(fi * 1000 + subsetKey.charCodeAt(0) * 13)
    const n = 60 + Math.floor(rng() * 15)
    for (let i = 0; i < n; i++) {
      const r = rng()
      const u = rng() || 0.0001
      const v = rng() || 0.0001
      const gauss = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
      const shap = (f.sign * (0.05 + r * 0.4) + gauss * 0.06) * f.spread * mod
      const rawNorm = f.sign < 0
        ? Math.max(0, Math.min(1, 0.5 - shap * 1.5 + (rng() - 0.5) * 0.4))
        : Math.max(0, Math.min(1, 0.5 + shap * 1.5 + (rng() - 0.5) * 0.4))
      const raw = f.range[0] + rawNorm * (f.range[1] - f.range[0])
      const jitter = (rng() - 0.5) * 0.62
      points.push({ fi, shap, raw, rawNorm, yPos: fi + jitter })
    }
  })
  return { features: feats.map((f) => f.name), points }
}

function rawColor(t: number): string {
  // [0, 1] → blue → tan → red
  const lo = t < 0.5
    ? { t: 0, rgb: [107, 168, 181] as [number, number, number], hi: { t: 0.5, rgb: [200, 175, 130] as [number, number, number] } }
    : { t: 0.5, rgb: [200, 175, 130] as [number, number, number], hi: { t: 1, rgb: [216, 145, 111] as [number, number, number] } }
  const k = (t - lo.t) / (lo.hi.t - lo.t || 1)
  const r = Math.round(lo.rgb[0] + (lo.hi.rgb[0] - lo.rgb[0]) * k)
  const g = Math.round(lo.rgb[1] + (lo.hi.rgb[1] - lo.rgb[1]) * k)
  const b = Math.round(lo.rgb[2] + (lo.hi.rgb[2] - lo.rgb[2]) * k)
  return `rgb(${r},${g},${b})`
}

const importanceEl = ref<HTMLDivElement | null>(null)
const waterfallEl = ref<HTMLDivElement | null>(null)
const beeswarmEl = ref<HTMLDivElement | null>(null)

let importanceChart: echarts.ECharts | null = null
let waterfallChart: echarts.ECharts | null = null
let beeswarmChart: echarts.ECharts | null = null
let resizeHandler: (() => void) | null = null

function renderImportance() {
  if (!importanceChart) return
  const f = features.value
  importanceChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 100, right: 60, top: 14, bottom: 28 },
      tooltip: {
        trigger: 'item',
        backgroundColor: getCSSVar('--bg-elev'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 12 },
        formatter: (p: { dataIndex: number; value: number }) => {
          const ft = f[f.length - 1 - p.dataIndex]
          const color = ft.dir === 'green' ? getCSSVar('--green-bright') : getCSSVar('--risk-4')
          const tag = ft.dir === 'green' ? '韧性因子 · 降风险' : '致灾因子 · 推风险'
          return `<b>${ft.name}</b> <span style="color:${getCSSVar('--text-3')};font-family:JetBrains Mono;font-size:10px;">${ft.en}</span><br/>
            <span style="font-family:JetBrains Mono;color:${color};font-size:16px;font-weight:600;">${p.value.toFixed(3)}</span><br/>
            <span style="font-size:11px;color:${getCSSVar('--text-2')};">${tag}</span>`
        },
      },
      xAxis: {
        type: 'value',
        max: 0.55,
        splitLine: { lineStyle: { color: getCSSVar('--border'), type: 'dashed' } },
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text-3'), fontFamily: 'JetBrains Mono', fontSize: 10 },
      },
      yAxis: {
        type: 'category',
        data: f.slice().reverse().map((x) => x.name),
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text'), fontFamily: 'Noto Sans SC', fontSize: 12, fontWeight: 500 },
        axisTick: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: f.slice().reverse().map((x) => ({
            value: x.shap,
            itemStyle: {
              color: {
                type: 'linear',
                x: 0, y: 0, x2: 1, y2: 0,
                colorStops: x.dir === 'green'
                  ? [{ offset: 0, color: getCSSVar('--green-deep') }, { offset: 1, color: getCSSVar('--green-bright') }]
                  : [{ offset: 0, color: getCSSVar('--risk-5') }, { offset: 1, color: getCSSVar('--risk-4') }],
              },
              borderRadius: [0, 3, 3, 0],
            },
          })),
          barWidth: 16,
          label: {
            show: true,
            position: 'right',
            color: getCSSVar('--text'),
            fontFamily: 'JetBrains Mono',
            fontSize: 11,
            fontWeight: 500,
            formatter: (p: { value: number }) => p.value.toFixed(3),
          },
          animationDuration: 800,
        },
      ],
    },
    true,
  )
}

function renderWaterfall() {
  if (!waterfallChart) return

  let cumulative = 0
  const placeholder: Array<number | string> = []
  const positive: Array<number | string> = []
  const negative: Array<number | string> = []
  const totalBar: Array<{ value: number; itemStyle: { color: string; borderRadius: number } } | string> = []
  const labels = WATERFALL_STEPS.map((s) => s.name)

  WATERFALL_STEPS.forEach((step) => {
    if (step.type === 'baseline') {
      placeholder.push('-'); positive.push('-'); negative.push('-')
      totalBar.push({ value: step.val!, itemStyle: { color: getCSSVar('--amber'), borderRadius: 2 } })
      cumulative = step.val!
    } else if (step.type === 'final') {
      placeholder.push('-'); positive.push('-'); negative.push('-')
      totalBar.push({ value: step.val!, itemStyle: { color: getCSSVar('--blue'), borderRadius: 2 } })
    } else if (step.type === 'pos') {
      placeholder.push(cumulative); positive.push(step.delta!); negative.push('-'); totalBar.push('-')
      cumulative += step.delta!
    } else {
      cumulative += step.delta!
      placeholder.push(cumulative); positive.push('-'); negative.push(-step.delta!); totalBar.push('-')
    }
  })

  waterfallChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 60, right: 50, top: 14, bottom: 78 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(160,183,133,0.06)' } },
        backgroundColor: getCSSVar('--bg-elev'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 12 },
        formatter: (params: Array<{ dataIndex: number }>) => {
          const step = WATERFALL_STEPS[params[0].dataIndex]
          if (step.type === 'baseline' || step.type === 'final') {
            const c = step.type === 'baseline' ? getCSSVar('--amber') : getCSSVar('--blue')
            return `<b>${step.name}</b><br/><span style="font-family:JetBrains Mono;font-size:15px;font-weight:600;color:${c};">${step.val!.toFixed(4)}</span>`
          }
          const sign = step.delta! >= 0 ? '+' : ''
          const color = step.delta! >= 0 ? getCSSVar('--risk-4') : getCSSVar('--green-bright')
          return `<b>${step.name}</b><br/><span style="font-family:JetBrains Mono;font-size:15px;font-weight:600;color:${color};">${sign}${step.delta!.toFixed(4)}</span><br/>
            <span style="font-size:11px;color:${getCSSVar('--text-2')};">${step.delta! >= 0 ? '推高风险' : '降低风险'}</span>`
        },
      },
      xAxis: {
        type: 'category',
        data: labels,
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text-2'), fontFamily: 'Noto Sans SC', fontSize: 10, interval: 0, rotate: 32 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        min: 0.02,
        max: 0.028,
        splitLine: { lineStyle: { color: getCSSVar('--border'), type: 'dashed' } },
        axisLine: { show: false },
        axisLabel: { color: getCSSVar('--text-3'), fontFamily: 'JetBrains Mono', fontSize: 10, formatter: (v: number) => v.toFixed(4) },
      },
      series: [
        { name: 'placeholder', type: 'bar', stack: 'all', data: placeholder, itemStyle: { color: 'transparent' }, silent: true },
        {
          name: '推升',
          type: 'bar',
          stack: 'all',
          data: positive,
          itemStyle: { color: getCSSVar('--risk-4'), borderRadius: 2 },
          label: {
            show: true,
            position: 'top',
            color: getCSSVar('--risk-4'),
            fontFamily: 'JetBrains Mono',
            fontSize: 10,
            fontWeight: 600,
            formatter: (p: { value: number | string }) => (p.value === '-' ? '' : '+' + (p.value as number).toFixed(4)),
          },
          barWidth: 22,
        },
        {
          name: '降低',
          type: 'bar',
          stack: 'all',
          data: negative,
          itemStyle: { color: getCSSVar('--green'), borderRadius: 2 },
          label: {
            show: true,
            position: 'bottom',
            color: getCSSVar('--green-bright'),
            fontFamily: 'JetBrains Mono',
            fontSize: 10,
            fontWeight: 600,
            formatter: (p: { value: number | string }) => (p.value === '-' ? '' : '−' + (p.value as number).toFixed(4)),
          },
          barWidth: 22,
        },
        {
          name: '基线/终点',
          type: 'bar',
          data: totalBar,
          label: {
            show: true,
            position: 'top',
            color: getCSSVar('--text'),
            fontFamily: 'JetBrains Mono',
            fontSize: 11,
            fontWeight: 600,
            formatter: (p: { value: number | string }) => (p.value === '-' ? '' : (p.value as number).toFixed(4)),
          },
          barWidth: 22,
        },
      ],
      animationDuration: 800,
    },
    true,
  )
}

function renderBeeswarm() {
  if (!beeswarmChart) return
  const { features: featNames, points } = generateBeeswarmPoints(subset.value)
  const seriesData = featNames.map((_, fi) =>
    points
      .filter((p) => p.fi === fi)
      .map((p) => ({
        value: [p.shap, p.yPos, p.raw, p.rawNorm],
        itemStyle: { color: rawColor(p.rawNorm), opacity: 0.72 },
      })),
  )

  beeswarmChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 92, right: 24, top: 14, bottom: 56 },
      tooltip: {
        trigger: 'item',
        backgroundColor: getCSSVar('--bg-elev'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 12 },
        formatter: (p: { value: [number, number, number, number] }) => {
          const fi = Math.round(p.value[1])
          const fname = featNames[Math.max(0, Math.min(4, fi))]
          const sign = p.value[0] >= 0 ? '+' : ''
          const color = p.value[0] >= 0 ? getCSSVar('--risk-4') : getCSSVar('--green-bright')
          return `<b>${fname}</b><br/><span style="font-family:JetBrains Mono;font-size:14px;color:${color};font-weight:600;">SHAP ${sign}${p.value[0].toFixed(3)}</span><br/>
            <span style="font-size:11px;color:${getCSSVar('--text-2')};">原始值 ${p.value[2].toFixed(1)}</span>`
        },
      },
      xAxis: {
        type: 'value',
        min: -0.5, max: 0.5,
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text-3'), fontFamily: 'JetBrains Mono', fontSize: 10 },
        splitLine: { show: false },
        name: 'SHAP value · ← 减损   增灾 →',
        nameLocation: 'middle',
        nameGap: 26,
        nameTextStyle: { color: getCSSVar('--text-3'), fontFamily: 'JetBrains Mono', fontSize: 10, fontWeight: 500 },
      },
      yAxis: {
        type: 'value',
        min: -0.5, max: 4.5,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: getCSSVar('--border'), type: 'dashed', opacity: 0.5 } },
        axisLabel: {
          color: getCSSVar('--text'),
          fontFamily: 'Noto Sans SC',
          fontSize: 11,
          fontWeight: 500,
          formatter: (v: number) => featNames[v] || '',
          interval: 0,
        },
      },
      series: featNames.map((fname, fi) => ({
        name: fname,
        type: 'scatter',
        data: seriesData[fi],
        symbolSize: 6.5,
        markLine: fi === 0
          ? { silent: true, symbol: 'none', lineStyle: { color: getCSSVar('--border-strong'), type: 'solid', width: 1 }, data: [{ xAxis: 0, label: { show: false } }] }
          : undefined,
      })),
      animationDuration: 600,
      animationDelay: (idx: number) => idx * 2,
    },
    true,
  )
}

function rerenderAll() {
  renderImportance()
  renderWaterfall()
  renderBeeswarm()
}

watch(subset, () => {
  renderImportance()
  renderBeeswarm()
})

onMounted(() => {
  if (importanceEl.value) importanceChart = echarts.init(importanceEl.value, undefined, { renderer: 'canvas' })
  if (waterfallEl.value) waterfallChart = echarts.init(waterfallEl.value, undefined, { renderer: 'canvas' })
  if (beeswarmEl.value) beeswarmChart = echarts.init(beeswarmEl.value, undefined, { renderer: 'canvas' })
  rerenderAll()
  resizeHandler = () => {
    importanceChart?.resize()
    waterfallChart?.resize()
    beeswarmChart?.resize()
  }
  window.addEventListener('resize', resizeHandler)
})

onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  importanceChart?.dispose()
  waterfallChart?.dispose()
  beeswarmChart?.dispose()
})
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M02 · SHAP ATTRIBUTION DASHBOARD</div>
      <h2>SHAP 归因看板</h2>
      <p class="lead">
        XGBoost-SHAP 三维度可解释性归因：全局重要性 / 单样本预测分解 / 蜂群分布。
        本视图为 mock 数据演示（Phase 2 后接入 <code>backend/models/xgb_model.pkl</code> 真 SHAP 值，
        熊鑫 5/26 上传 .pkl/.h5 后由 <code>/api/shap/*</code> 提供）。
      </p>
    </header>

    <!-- 顶部 subset selector + meta -->
    <div class="subset-bar card">
      <div class="subset-head">
        <div>
          <div class="num">M02-0 · SUBSET</div>
          <h3>样本子集切换</h3>
        </div>
        <div class="meta">
          <span>样本 N <span class="v">{{ currentSubset.sampleN }}</span></span>
          <span>覆盖 <span class="v">{{ currentSubset.cover }}</span> 省</span>
        </div>
      </div>
      <div class="seg">
        <button
          v-for="s in SUBSETS"
          :key="s.key"
          class="seg-btn"
          :class="{ active: subset === s.key }"
          @click="subset = s.key"
        >
          {{ s.label }}
        </button>
      </div>
    </div>

    <!-- 主 grid 3 chart -->
    <div class="grid">
      <div class="card chart-card">
        <div class="card-head">
          <div>
            <div class="num">M02-A · GLOBAL IMPORTANCE</div>
            <h3>全局特征重要性 mean(|SHAP|)</h3>
          </div>
          <span class="hint">绿色 = 韧性因子，赭石 = 致灾因子</span>
        </div>
        <div ref="importanceEl" class="chart-canvas"></div>
      </div>

      <div class="card chart-card">
        <div class="card-head">
          <div>
            <div class="num">M02-B · WATERFALL · 河南 2022</div>
            <h3>单样本预测分解</h3>
          </div>
          <span class="hint">E[f(x)] = {{ WATERFALL_STEPS[0].val }} → f(x) = {{ WATERFALL_STEPS[WATERFALL_STEPS.length - 1].val }}</span>
        </div>
        <div ref="waterfallEl" class="chart-canvas"></div>
      </div>

      <div class="card chart-card full">
        <div class="card-head">
          <div>
            <div class="num">M02-C · BEESWARM</div>
            <h3>Top 5 特征 SHAP 蜂群分布</h3>
          </div>
          <span class="hint">点色 = 原始值（蓝低 → 赭石高）&nbsp;·&nbsp;X = SHAP 值</span>
        </div>
        <div ref="beeswarmEl" class="chart-canvas"></div>
      </div>
    </div>

    <footer class="page-foot">
      <a href="/prototypes/02-shap-dashboard.html" target="_blank" class="proto-link">查看原型 HTML ↗</a>
      <span class="note">11 特征 mean(|SHAP|) 来自 prototype mock；Phase 2 接入熊鑫 .pkl 真模型 + shap 库</span>
    </footer>
  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1480px; margin: 0 auto; }

.page-head { margin-bottom: 20px; }
.eyebrow { font-family: var(--font-mono); font-size: 10px; color: var(--green); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 8px; }
.page-head h2 { font-family: var(--font-serif); font-size: 26px; font-weight: 600; margin-bottom: 6px; }
.lead { font-size: 13px; color: var(--text-2); max-width: 920px; line-height: 1.7; }
.lead code { font-family: var(--font-mono); background: var(--bg-elev); padding: 1px 6px; border-radius: 3px; font-size: 11px; }

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
.card-head .num { font-family: var(--font-mono); font-size: 9px; color: var(--text-3); letter-spacing: 1px; margin-bottom: 2px; }
.card-head h3 { font-family: var(--font-serif); font-size: 14px; font-weight: 600; }
.card-head .hint { font-family: var(--font-mono); font-size: 10px; color: var(--text-3); }

/* subset bar */
.subset-bar { margin-bottom: 16px; }
.subset-head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 12px; }
.subset-head .meta {
  display: flex;
  gap: 16px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
}
.subset-head .v { color: var(--green-bright); font-weight: 600; margin-left: 4px; }

.seg {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--bg-elev);
  border-radius: var(--r-md);
}
.seg-btn {
  flex: 1;
  padding: 8px 14px;
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-2);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--dur-fast);
}
.seg-btn:hover { color: var(--text); }
.seg-btn.active {
  background: var(--bg-card);
  color: var(--green-bright);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

/* main grid */
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 420px 420px;
  gap: 16px;
}
.chart-card { display: flex; flex-direction: column; }
.chart-card.full { grid-column: 1 / -1; }
.chart-canvas { flex: 1; min-height: 0; }

.page-foot {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--text-3);
  gap: 16px;
}
.page-foot .note { font-family: var(--font-mono); text-align: right; }
.page-foot .note code { background: var(--bg-elev); padding: 1px 5px; border-radius: 2px; font-size: 10px; }
.proto-link {
  flex-shrink: 0;
  padding: 6px 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--green-bright);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.3px;
  transition: all var(--dur-fast);
}
.proto-link:hover { border-color: var(--green); transform: translateY(-1px); }
</style>
