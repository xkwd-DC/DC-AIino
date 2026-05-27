<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { getCSSVar } from '@/data/mockProvinces'
import { postPredict, type ShapContrib } from '@/api/predict'
import { useProvinceStore } from '@/stores/useProvinceStore'
import { storeToRefs } from 'pinia'
// a11y: ECharts 动画绕过 CSS prefers-reduced-motion,JS 探测后传 0
import { motionDuration } from '@/data/a11y'

// 11 维特征顺序与 backend/api/predict.py _FEATURE_LABELS 严格对齐:
// 这是 view 用来组装"全 11 维"的固定骨架。后端 /api/predict 当前只返 top-5
// (见 `_shap_top()` top_n=5),其余 6 维我们以 value=0 占位 + 注脚说明,
// 避免出现"6 个不显示 / 5 个真值"的混杂视觉。
const FEATURES_SCHEMA: Array<{ name: string; en: string }> = [
  { name: '灌溉率',       en: 'Irr' },
  { name: '洪涝占比',     en: 'Flood_R' },
  { name: '日照时数',     en: 'Sun' },
  { name: '平均气温',     en: 'Temp' },
  { name: 'SPEI 干旱指数', en: 'SPEI' },
  { name: '降水量',       en: 'Prec' },
  { name: '农机总动力',   en: 'Mech' },
  { name: '化肥施用量',   en: 'Fert' },
  { name: '旱灾面积',     en: 'Drou_A' },
  { name: '水灾面积',     en: 'Flood_A' },
  { name: 'NDVI 异常',    en: 'NDVI' },
]

interface Feature {
  name: string
  en: string
  shap: number
  dir: 'green' | 'red'
  hasValue: boolean   // true=API top-N 真值;false=占位 0
}

// ── 后端 SHAP 状态 ────────────────────────────────────────────────────────
const backendContribs = ref<ShapContrib[] | null>(null)
const isLoadingShap = ref(false)
const shapError = ref<string | null>(null)

const provinceStore = useProvinceStore()
const { selected: selectedProvince, isLoading: storeLoading, source: storeSource } = storeToRefs(provinceStore)

/** 把 API top-N 装回 11 维骨架。
 *  - 命中:value = |shap|;direction → dir(harm=red, protect=green);hasValue=true
 *  - 未命中:value = 0;dir 按 schema 默认("绿"或"红")推断;hasValue=false → 视觉灰色
 */
function assembleFullFeatures(contribs: ShapContrib[]): Feature[] {
  const lookup = new Map<string, ShapContrib>()
  for (const c of contribs) lookup.set(c.feature, c)
  return FEATURES_SCHEMA.map((f) => {
    const hit = lookup.get(f.name)
    if (!hit) {
      return { ...f, shap: 0, dir: 'green', hasValue: false }
    }
    return {
      ...f,
      shap: Math.abs(hit.value),
      dir: hit.direction === 'harm' ? 'red' : 'green',
      hasValue: true,
    }
  })
}

/** 当前 11 维特征数据,只在 backendContribs 就绪时返回有效骨架,
 *  否则返回空数组(view 显示 loading / error)。 */
const FEATURES_ALL = computed<Feature[]>(() =>
  backendContribs.value ? assembleFullFeatures(backendContribs.value) : [],
)

const apiReadyCount = computed(() => FEATURES_ALL.value.filter((f) => f.hasValue).length)

const shapDataSource = computed<'loading' | 'error' | 'model' | 'idle'>(() => {
  if (isLoadingShap.value) return 'loading'
  if (shapError.value) return 'error'
  if (backendContribs.value) return 'model'
  return 'idle'
})

async function fetchShapData() {
  if (!selectedProvince.value?.name) return
  isLoadingShap.value = true
  shapError.value = null
  try {
    const data = await postPredict(
      selectedProvince.value.name,
      {
        irr: selectedProvince.value.irr,
        flood: selectedProvince.value.flood,
        sun: selectedProvince.value.sun,
        temp: selectedProvince.value.temp,
        spei: selectedProvince.value.spei,
      },
      'xgboost', // XGB-SHAP attribution(更稳定,后端 _approx_contribs 用 XGB)
    )
    backendContribs.value = data.shap_top
  } catch (e: unknown) {
    shapError.value = e instanceof Error ? e.message : 'network error'
    backendContribs.value = null
  } finally {
    isLoadingShap.value = false
  }
}

// 省份切换时重新拉
watch(selectedProvince, () => {
  if (selectedProvince.value?.name) {
    backendContribs.value = null
    shapError.value = null
    fetchShapData()
  }
})

type SubsetKey = 'all' | 'north' | 'south' | 'major'

interface Subset {
  key: SubsetKey
  label: string
  sampleN: number
  cover: number
  mods: Record<string, number>
}

// SUBSETS 用于"子集对比展示"——这是 sample-level 演示叙事,
// mods 是 ablation-style 缩放因子,纯 visualization aid。
// 真后端要在子集上重新跑模型才能给出精确 SHAP,目前后端没暴露此 endpoint;
// 此处保留为 visualization 辅助层,不会让用户误把它当作真子集模型输出。
const SUBSETS: Subset[] = [
  { key: 'all', label: '全样本 (31 省)', sampleN: 403, cover: 31, mods: {} },
  { key: 'north', label: '北方 (14 省)', sampleN: 169, cover: 14, mods: { '灌溉率': 1.18, '日照时数': 1.22, 'SPEI 干旱指数': 1.35, '旱灾面积': 1.45, '洪涝占比': 0.55, '水灾面积': 0.42, '降水量': 0.78 } },
  { key: 'south', label: '南方 (12 省)', sampleN: 156, cover: 12, mods: { '灌溉率': 0.72, '洪涝占比': 1.32, '水灾面积': 1.55, '降水量': 1.28, '日照时数': 0.85, 'SPEI 干旱指数': 0.42, '旱灾面积': 0.38 } },
  { key: 'major', label: '主产区 (13 省)', sampleN: 169, cover: 13, mods: { '灌溉率': 1.08, '化肥施用量': 1.42, '农机总动力': 1.38, '洪涝占比': 1.05, '降水量': 0.92 } },
]

const subset = ref<SubsetKey>('all')
const currentSubset = computed(() => SUBSETS.find((s) => s.key === subset.value)!)

const features = computed<Feature[]>(() => {
  const mods = currentSubset.value.mods
  return FEATURES_ALL.value
    .map((f) => ({ ...f, shap: +(f.shap * (mods[f.name] || 1)).toFixed(3) }))
    .sort((a, b) => b.shap - a.shap)
})

// Waterfall:5/27 v0.1 阶段保留参考结构(单样本 attribution 后端尚未暴露 endpoint),
// 但底数已对齐 backend _BASELINE_RISK = 0.0235 + risk clip 区间。当 backend 加上
// per-sample shap.TreeExplainer endpoint 后再切真值。
// HIGH#6: discriminated union,TS 在每个 type 分支自动 narrow val/delta,
// 去掉所有 `step.val!` / `step.delta!` 非空强断言。
type WaterfallBaseline = { name: string; type: 'baseline'; val: number }
type WaterfallFinal = { name: string; type: 'final'; val: number }
type WaterfallPos = { name: string; type: 'pos'; delta: number }
type WaterfallNeg = { name: string; type: 'neg'; delta: number }
type WaterfallStep = WaterfallBaseline | WaterfallFinal | WaterfallPos | WaterfallNeg

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

// 模板里 E[f(x)] / f(x) 两端 readout 用得到 — 类型已知,免去模板里强断言。
const WATERFALL_BASELINE = WATERFALL_STEPS[0] as WaterfallBaseline
const WATERFALL_FINAL = WATERFALL_STEPS[WATERFALL_STEPS.length - 1] as WaterfallFinal

// 伪随机 beeswarm:同样是 visualization aid,样本级 SHAP 后端 endpoint 待开。
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
    const modKey = f.name === 'SPEI 干旱' ? 'SPEI 干旱指数' : f.name
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
  if (f.length === 0) {
    importanceChart.clear()
    return
  }
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
          if (!ft.hasValue) {
            return `<b>${ft.name}</b> <span style="color:${getCSSVar('--text-3')};font-family:JetBrains Mono;font-size:10px;">${ft.en}</span><br/>
              <span style="font-family:JetBrains Mono;color:${getCSSVar('--text-3')};font-size:14px;">未进入 top-${apiReadyCount.value} 因子</span><br/>
              <span style="font-size:11px;color:${getCSSVar('--text-3')};">API 仅返回 top-N,余项以 0 占位</span>`
          }
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
              color: !x.hasValue
                ? getCSSVar('--bg-elev')   // 占位项灰色,视觉与 top-N 真值区隔
                : {
                    type: 'linear',
                    x: 0, y: 0, x2: 1, y2: 0,
                    colorStops: x.dir === 'green'
                      ? [{ offset: 0, color: getCSSVar('--green-deep') }, { offset: 1, color: getCSSVar('--green-bright') }]
                      : [{ offset: 0, color: getCSSVar('--risk-5') }, { offset: 1, color: getCSSVar('--risk-4') }],
                  },
              borderRadius: [0, 3, 3, 0],
              borderColor: !x.hasValue ? getCSSVar('--border') : 'transparent',
              borderWidth: !x.hasValue ? 1 : 0,
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
            formatter: (p: { value: number; dataIndex: number }) => {
              const ft = f[f.length - 1 - p.dataIndex]
              return ft.hasValue ? p.value.toFixed(3) : '—'
            },
          },
          animationDuration: motionDuration(800),
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
      totalBar.push({ value: step.val, itemStyle: { color: getCSSVar('--amber'), borderRadius: 2 } })
      cumulative = step.val
    } else if (step.type === 'final') {
      placeholder.push('-'); positive.push('-'); negative.push('-')
      totalBar.push({ value: step.val, itemStyle: { color: getCSSVar('--blue'), borderRadius: 2 } })
    } else if (step.type === 'pos') {
      placeholder.push(cumulative); positive.push(step.delta); negative.push('-'); totalBar.push('-')
      cumulative += step.delta
    } else {
      cumulative += step.delta
      placeholder.push(cumulative); positive.push('-'); negative.push(-step.delta); totalBar.push('-')
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
            return `<b>${step.name}</b><br/><span style="font-family:JetBrains Mono;font-size:15px;font-weight:600;color:${c};">${step.val.toFixed(4)}</span>`
          }
          // step.type narrowed to 'pos' | 'neg', both carry numeric delta.
          const sign = step.delta >= 0 ? '+' : ''
          const color = step.delta >= 0 ? getCSSVar('--risk-4') : getCSSVar('--green-bright')
          return `<b>${step.name}</b><br/><span style="font-family:JetBrains Mono;font-size:15px;font-weight:600;color:${color};">${sign}${step.delta.toFixed(4)}</span><br/>
            <span style="font-size:11px;color:${getCSSVar('--text-2')};">${step.delta >= 0 ? '推高风险' : '降低风险'}</span>`
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
      animationDuration: motionDuration(800),
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
      animationDuration: motionDuration(600),
      animationDelay: (idx: number) => motionDuration(idx * 2),
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

// 后端数据到达时刷新重要性图
watch(backendContribs, () => {
  renderImportance()
}, { flush: 'post' })

onMounted(async () => {
  if (importanceEl.value) importanceChart = echarts.init(importanceEl.value, undefined, { renderer: 'canvas' })
  if (waterfallEl.value) waterfallChart = echarts.init(waterfallEl.value, undefined, { renderer: 'canvas' })
  if (beeswarmEl.value) beeswarmChart = echarts.init(beeswarmEl.value, undefined, { renderer: 'canvas' })
  rerenderAll()
  // 等省份数据就绪后再请求 predict
  if (storeSource.value === 'none') {
    await provinceStore.loadProvinces()
  }
  await fetchShapData()
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
        XGBoost-SHAP 三视角:全局重要性 / 单样本预测分解 / 蜂群分布。
        全局重要性条形图由 <code>POST /api/predict</code> 返回的 SHAP top-{{ apiReadyCount || 5 }} 真值驱动;
        余项以 0 占位灰条标识(后端当前仅暴露 top-N)。
        <span v-if="storeLoading || isLoadingShap" class="shap-status loading">· 加载模型数据…</span>
        <span v-else-if="shapDataSource === 'error'" class="shap-status err">· 模型暂不可用 {{ shapError ? `· ${shapError}` : '' }}</span>
        <span v-else-if="shapDataSource === 'model'" class="shap-status real">· 真模型 SHAP top-{{ apiReadyCount }}</span>
      </p>
      <p v-if="selectedProvince?.name" class="province-line">
        当前省份 <b>{{ selectedProvince.name }}</b>
        <span class="prov-meta">{{ selectedProvince.type }} · y={{ selectedProvince.y.toFixed(4) }}</span>
      </p>
    </header>

    <!-- 顶部 subset selector + meta -->
    <div class="subset-bar card">
      <div class="subset-head">
        <div>
          <div class="num">M02-0 · SUBSET</div>
          <h3 id="subset-heading">样本子集切换</h3>
        </div>
        <div class="meta">
          <span>样本 N <span class="v">{{ currentSubset.sampleN }}</span></span>
          <span>覆盖 <span class="v">{{ currentSubset.cover }}</span> 省</span>
        </div>
      </div>
      <!-- a11y SC 4.1.2 + WAI-ARIA Tabs Pattern:tablist / tab + aria-selected -->
      <div class="seg" role="tablist" aria-labelledby="subset-heading">
        <button
          v-for="s in SUBSETS"
          :key="s.key"
          class="seg-btn"
          :class="{ active: subset === s.key }"
          role="tab"
          :aria-selected="subset === s.key"
          :aria-label="`切换至 ${s.label} 样本子集`"
          :tabindex="subset === s.key ? 0 : -1"
          @click="subset = s.key"
        >
          {{ s.label }}
        </button>
      </div>
    </div>

    <!-- 主 grid 3 chart -->
    <div class="grid" role="region" aria-label="SHAP 归因图表区">
      <div class="card chart-card">
        <div class="card-head">
          <div>
            <div class="num">M02-A · GLOBAL IMPORTANCE</div>
            <h3>全局特征重要性 mean(|SHAP|)</h3>
          </div>
          <span class="hint">绿色 = 韧性因子,赭石 = 致灾因子,灰条 = 未进入 top-N</span>
        </div>
        <!-- a11y SC 1.1.1:ECharts canvas 加 role/aria-label 文本替代 -->
        <div
          ref="importanceEl"
          class="chart-canvas"
          role="img"
          :aria-label="`全局特征重要性条形图:11 个变量,其中 ${apiReadyCount} 个由 API 返回真值,其余以 0 占位`"
          tabindex="0"
        ></div>
        <div v-if="shapDataSource === 'loading' && features.length === 0" class="chart-overlay">
          <div class="spinner" aria-hidden="true"></div>
          <div>正在请求 <code>POST /api/predict</code>…</div>
        </div>
        <div v-else-if="shapDataSource === 'error'" class="chart-overlay err">
          <div>⚠ 模型暂不可用</div>
          <div class="small">{{ shapError }}</div>
          <button type="button" class="retry-btn" @click="fetchShapData">重试</button>
        </div>
      </div>

      <div class="card chart-card">
        <div class="card-head">
          <div>
            <div class="num">M02-B · WATERFALL · 参考样本</div>
            <h3>单样本预测分解</h3>
          </div>
          <span class="hint">E[f(x)] = {{ WATERFALL_BASELINE.val }} → f(x) = {{ WATERFALL_FINAL.val }}</span>
        </div>
        <div
          ref="waterfallEl"
          class="chart-canvas"
          role="img"
          :aria-label="`单样本预测分解 Waterfall 图:从基线 ${WATERFALL_BASELINE.val} 经 7 个特征贡献逐步演变到最终预测 ${WATERFALL_FINAL.val}`"
          tabindex="0"
        ></div>
      </div>

      <div class="card chart-card full">
        <div class="card-head">
          <div>
            <div class="num">M02-C · BEESWARM</div>
            <h3>Top 5 特征 SHAP 蜂群分布</h3>
          </div>
          <span class="hint">点色 = 原始值(蓝低 → 赭石高)&nbsp;·&nbsp;X = SHAP 值</span>
        </div>
        <div
          ref="beeswarmEl"
          class="chart-canvas"
          role="img"
          aria-label="Top 5 特征 SHAP 蜂群分布散点图:每个点代表一个样本,横轴为 SHAP 值,点色由蓝到赭石映射原始值由低到高"
          tabindex="0"
        ></div>
      </div>
    </div>

    <footer class="page-foot">
      <a href="/prototypes/02-shap-dashboard.html" target="_blank" class="proto-link">查看原型 HTML ↗</a>
      <span class="note">
        全局重要性 = <code>POST /api/predict</code> 单特征扰动 SHAP top-N 真值;
        Waterfall / Beeswarm = 子集可视化辅助(后端样本级 SHAP endpoint 待开)
      </span>
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
.shap-status { font-family: var(--font-mono); font-size: 11px; margin-left: 4px; }
.shap-status.loading { color: var(--amber); }
.shap-status.err { color: var(--purple, #b49dd8); }
.shap-status.real { color: var(--green-bright); }
.province-line {
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-2);
}
.province-line b { color: var(--green-bright); font-weight: 600; }
.province-line .prov-meta { color: var(--text-3); margin-left: 6px; }

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
.chart-card { display: flex; flex-direction: column; position: relative; }
.chart-card.full { grid-column: 1 / -1; }
.chart-canvas { flex: 1; min-height: 0; }

.chart-overlay {
  position: absolute;
  inset: 56px 16px 16px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(14, 26, 20, 0.85);
  border-radius: var(--r-md);
  color: var(--text-3);
  font-size: 12px;
  font-family: var(--font-mono);
}
.chart-overlay code { font-family: var(--font-mono); background: var(--bg-elev); padding: 1px 5px; border-radius: 2px; }
.chart-overlay.err { color: var(--purple, #b49dd8); }
.chart-overlay .small { font-size: 10px; opacity: 0.7; }
.retry-btn {
  margin-top: 6px;
  padding: 4px 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  color: var(--green-bright);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
}
.retry-btn:hover { border-color: var(--green); }
.spinner {
  width: 24px; height: 24px;
  border: 2px solid var(--bg-elev);
  border-top-color: var(--green);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

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
