<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import * as echarts from 'echarts'
import { PROVINCES_PROFILE } from '@/data/recommendation'
import { useProvinceStore } from '@/stores/useProvinceStore'
import { getCSSVar } from '@/data/mockProvinces'
import { postPredictDebounced, type PredictData } from '@/api/predict'
import {
  fetchGrowthCounties,
  postGrowthSimulate,
  type GrowthCountiesData,
  type GrowthCounty,
  type GrowthResult,
} from '@/api/growth'
// a11y: ECharts 动画绕过 CSS prefers-reduced-motion
import { motionDuration } from '@/data/a11y'

// HIGH#7: 200ms 防抖避免快拖滑块时 ECharts setOption 抖动 / stale render。
// 单文件极轻量实现，避免引入 lodash 整包。
function debounce<F extends (...args: never[]) => void>(fn: F, ms: number): F {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: Parameters<F>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }) as F
}

interface SliderDef {
  key: 'irr' | 'flood' | 'sun' | 'temp' | 'spei'
  label: string
  icon: string
  iconCls: 'green' | 'red' | 'amber' | 'purple'
  unit: string
  min: number
  max: number
  step: number
  hint: string
}

const SLIDERS: SliderDef[] = [
  { key: 'irr', label: '灌溉率', icon: '灌', iconCls: 'green', unit: '%', min: 20, max: 120, step: 0.5, hint: '↑ 越高风险越低' },
  { key: 'flood', label: '洪涝占比', icon: '洪', iconCls: 'red', unit: '%', min: 0, max: 24, step: 0.1, hint: '↑ 越高风险越高' },
  { key: 'sun', label: '日照时数', icon: '日', iconCls: 'amber', unit: 'h', min: 970, max: 3350, step: 5, hint: '↑ 越高风险越低' },
  { key: 'temp', label: '平均气温', icon: '温', iconCls: 'red', unit: '°C', min: 2, max: 26, step: 0.1, hint: '↑ 越高风险越高' },
  { key: 'spei', label: 'SPEI 干旱', icon: 'D', iconCls: 'purple', unit: '', min: -3, max: 3, step: 0.05, hint: '↑ 越湿润风险越低' },
]

// 与 backend/api/predict.py `_CENTERS` / `_COEFS` 对齐的 5 维瞬时反馈公式。
// 用前端公式 + 真后端 POST /api/predict 两条路径：前端实时（200ms 瞬时反馈，无网络延迟），真模型（XGBoost/LSTM/Attention-LSTM ensemble）异步覆盖（#45 已接通）。
const FORMULA_BASE = 0.0235
const MEANS: Record<SliderDef['key'], number> = { irr: 56.7, flood: 2.97, sun: 2086, temp: 14.0, spei: -0.08 }
const WEIGHTS: Record<SliderDef['key'], number> = {
  irr: -0.000115,
  flood: 0.000420,
  sun: -0.0000023,
  temp: 0.000180,
  spei: -0.000310,
}

function calcEffect(key: SliderDef['key'], val: number): number {
  return (val - MEANS[key]) * WEIGHTS[key]
}

function calcSimRisk(params: Record<SliderDef['key'], number>): number {
  let r = FORMULA_BASE
  for (const k of Object.keys(WEIGHTS) as Array<SliderDef['key']>) {
    r += calcEffect(k, params[k])
  }
  return Math.max(0.005, Math.min(0.055, r))
}

// HIGH#8: 改用 Pinia store 共享省份选择 — ResiliencePath.vue 同步切换。
const provinceStore = useProvinceStore()
const { selectedIdx, selected } = storeToRefs(provinceStore)

const baseline = computed(() => ({
  irr: selected.value.irr,
  flood: selected.value.flood,
  sun: selected.value.sun,
  temp: selected.value.temp,
  spei: selected.value.spei,
}))

const params = ref<Record<SliderDef['key'], number>>({ ...baseline.value })

// ── 前端公式：实时（拖滑块立即响应，无网络延迟）──────────────────────────
const frontendRisk = computed(() => calcSimRisk(params.value))

// ── 后端真值状态 ─────────────────────────────────────────────────────────
const backendRisk = ref<number | null>(null)   // null = 尚未拿到 / 后端不可用
const isLoadingBackend = ref(false)
const backendUnavailable = ref(false)           // 超时 / 网络错误后 fallback

/** 展示用风险值：有后端返回用真值，否则用前端公式（标注 estimate）*/
const simRisk = computed(() =>
  backendRisk.value !== null ? backendRisk.value : frontendRisk.value,
)
const isEstimate = computed(() => backendRisk.value === null)

const delta = computed(() => simRisk.value - selected.value.y)
const deltaPct = computed(() => (delta.value / selected.value.y) * 100)
const isWorse = computed(() => delta.value > 0)

// ── 调用后端（200ms 防抖，来自 api/predict.ts）───────────────────────────
function fetchBackendRisk() {
  isLoadingBackend.value = true
  postPredictDebounced(
    selected.value.name,
    {
      irr: params.value.irr,
      flood: params.value.flood,
      sun: params.value.sun,
      temp: params.value.temp,
      spei: params.value.spei,
    },
    'ensemble',
    (data: PredictData) => {
      backendRisk.value = data.risk_score
      backendUnavailable.value = false
      isLoadingBackend.value = false
    },
    (_err: unknown) => {
      backendUnavailable.value = true
      backendRisk.value = null
      isLoadingBackend.value = false
    },
  )
}

// 省份切换时重置后端结果
watch(selected, () => {
  params.value = { ...baseline.value }
  backendRisk.value = null
  backendUnavailable.value = false
})

const gaugeBaseEl = ref<HTMLDivElement | null>(null)
const gaugeSimEl = ref<HTMLDivElement | null>(null)
const contribEl = ref<HTMLDivElement | null>(null)

let gaugeBase: echarts.ECharts | null = null
let gaugeSim: echarts.ECharts | null = null
let contribChart: echarts.ECharts | null = null
let resizeHandler: (() => void) | null = null

function gaugeOption(value: number, label: string, pointerColor: string) {
  return {
    backgroundColor: 'transparent',
    series: [
      {
        type: 'gauge',
        min: 0.005,
        max: 0.055,
        startAngle: 200,
        endAngle: -20,
        radius: '95%',
        center: ['50%', '62%'],
        progress: { show: false },
        axisLine: {
          lineStyle: {
            width: 12,
            color: [
              [0.3, getCSSVar('--green')],
              [0.55, getCSSVar('--amber')],
              [0.8, getCSSVar('--risk-4')],
              [1.0, getCSSVar('--risk-5')],
            ] as Array<[number, string]>,
          },
        },
        pointer: {
          icon: 'path://M2,0 L-2,0 L0,-65 Z',
          length: '70%',
          offsetCenter: [0, 0],
          itemStyle: { color: pointerColor },
          width: 4,
        },
        anchor: {
          show: true,
          showAbove: true,
          size: 10,
          itemStyle: { color: getCSSVar('--bg'), borderColor: pointerColor, borderWidth: 2 },
        },
        axisTick: { length: 5, lineStyle: { color: getCSSVar('--text-3'), width: 1 } },
        splitLine: { length: 9, lineStyle: { color: getCSSVar('--text-2'), width: 2 } },
        axisLabel: {
          distance: -16,
          color: getCSSVar('--text-3'),
          fontSize: 8,
          fontFamily: 'JetBrains Mono',
          formatter: (v: number) => (v < 0.01 ? '' : v.toFixed(2)),
        },
        title: { offsetCenter: [0, '32%'], color: getCSSVar('--text-3'), fontSize: 10, fontFamily: 'JetBrains Mono' },
        detail: {
          // a11y SC 2.3.3:reduced-motion 关闭数字滚动动画
          valueAnimation: motionDuration(600) > 0,
          offsetCenter: [0, '15%'],
          formatter: (v: number) => v.toFixed(4),
          color: pointerColor,
          fontSize: 22,
          fontFamily: 'JetBrains Mono',
          fontWeight: 600,
        },
        data: [{ value, name: label }],
        animationDuration: motionDuration(600),
        animationEasing: 'cubicOut',
      },
    ],
  }
}

function renderGauges() {
  if (!gaugeBase || !gaugeSim) return
  gaugeBase.setOption(gaugeOption(selected.value.y, '基线 BASE', getCSSVar('--amber')))
  const simColor = isWorse.value ? getCSSVar('--risk-4') : getCSSVar('--green-bright')
  gaugeSim.setOption(
    gaugeOption(simRisk.value, isWorse.value ? '模拟 ↑ WORSE' : '模拟 ↓ BETTER', simColor),
  )
}

function renderContrib() {
  if (!contribChart) return
  const effects = SLIDERS.map((def) => ({
    key: def.key,
    name: def.label,
    value: calcEffect(def.key, params.value[def.key]),
  })).sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
  const yData = effects.map((e) => e.name).reverse()
  const xData = effects.map((e) => e.value).reverse()

  contribChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 92, right: 70, top: 14, bottom: 28 },
      tooltip: {
        trigger: 'item',
        backgroundColor: getCSSVar('--bg-elev'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 12 },
        formatter: (p: { value: number; dataIndex: number }) => {
          const name = yData[p.dataIndex]
          const sign = p.value > 0 ? '+' : ''
          const color = p.value > 0 ? getCSSVar('--risk-4') : getCSSVar('--green-bright')
          return `<b>${name}</b><br/><span style="font-family:JetBrains Mono;color:${color};font-size:14px;font-weight:600;">${sign}${p.value.toFixed(4)}</span>`
        },
      },
      xAxis: {
        type: 'value',
        max: 0.008,
        min: -0.008,
        splitLine: { lineStyle: { color: getCSSVar('--border'), type: 'dashed' } },
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text-3'), fontFamily: 'JetBrains Mono', fontSize: 10, formatter: (v: number) => v.toFixed(3) },
      },
      yAxis: {
        type: 'category',
        data: yData,
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text'), fontFamily: 'Noto Sans SC', fontSize: 12, fontWeight: 500 },
        axisTick: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: xData.map((v) => ({
            value: v,
            itemStyle: {
              color: v > 0 ? getCSSVar('--risk-4') : getCSSVar('--green'),
              borderRadius: v > 0 ? [0, 3, 3, 0] : [3, 0, 0, 3],
            },
          })),
          barWidth: 22,
          label: {
            show: true,
            position: (p: { value: number }) => (p.value > 0 ? 'right' : 'left'),
            color: getCSSVar('--text'),
            fontFamily: 'JetBrains Mono',
            fontSize: 11,
            fontWeight: 500,
            formatter: (p: { value: number }) => (p.value > 0 ? '+' : '') + p.value.toFixed(4),
          },
          animationDuration: motionDuration(400),
          animationDurationUpdate: motionDuration(250),
        },
      ],
    },
    true,
  )
}

function rerender() {
  renderGauges()
  renderContrib()
}

// HIGH#7: 滑块快速拖拽时合并多次 watch trigger，flush:'post' 等 DOM 同步后再调
// ECharts setOption，避免 canvas 在 micro-tick 期间被多次重绘 / stale。
const debouncedRerender = debounce(rerender, 200)

// params 变化时：立即用前端公式重绘（无延迟），同时触发后端防抖请求
watch(params, () => {
  debouncedRerender()
  fetchBackendRisk()
}, { deep: true, flush: 'post' })

// backendRisk 变化时（后端返回真值）：刷新图表
watch(backendRisk, () => {
  debouncedRerender()
}, { flush: 'post' })

// 仅在 selected 变化时重绘（params 已在 watch(selected) 里重置）
watch(selected, debouncedRerender, { flush: 'post' })

function pctOf(val: number, def: SliderDef): number {
  return ((val - def.min) / (def.max - def.min)) * 100
}

function fmtVal(key: SliderDef['key'], val: number): string {
  if (key === 'sun') return Math.round(val).toString()
  if (key === 'spei') return val.toFixed(2)
  return val.toFixed(1)
}

function resetToBaseline() {
  params.value = { ...baseline.value }
}

// ── M03 玉米长势页签 ─────────────────────────────────────────────────────
type GrowthSliderKey = 'd_temp' | 'd_prec_pct' | 'd_heat_days' | 'irrigation'

interface GrowthSliderDef {
  key: GrowthSliderKey
  label: string
  icon: string
  iconCls: 'green' | 'red' | 'amber' | 'purple'
  unit: string
  min: number
  max: number
  step: number
  hint: string
}

const GROWTH_SLIDERS: GrowthSliderDef[] = [
  { key: 'd_temp', label: '温度增量', icon: '温', iconCls: 'red', unit: '°C', min: -2, max: 4, step: 0.1, hint: '升温抬高蒸散；热害日单独设定' },
  { key: 'd_prec_pct', label: '降水变化', icon: '雨', iconCls: 'purple', unit: '%', min: -40, max: 40, step: 1, hint: '生长季降水相对变化' },
  { key: 'd_heat_days', label: '高温日增量', icon: '热', iconCls: 'amber', unit: '天', min: 0, max: 30, step: 1, hint: '≥35°C 日数增加' },
  { key: 'irrigation', label: '灌溉保证率', icon: '灌', iconCls: 'green', unit: '%', min: 0, max: 100, step: 1, hint: '省级共享值，可手动覆盖' },
]

const activeTab = ref<'risk' | 'maize'>('risk')
const maizeRows = ref<GrowthCounty[]>([])
const maizeMeta = ref<GrowthCountiesData['meta'] | null>(null)
const maizeCode = ref<number | null>(null)
const maizeLoading = ref(false)
const maizeSimLoading = ref(false)
const maizeError = ref('')
const maizeResult = ref<GrowthResult | null>(null)
const maizeParams = ref<Record<GrowthSliderKey, number>>({
  d_temp: 0,
  d_prec_pct: 0,
  d_heat_days: 0,
  irrigation: 60,
})

const maizeCounty = computed(
  () => maizeRows.value.find((r) => r.code === maizeCode.value) ?? null,
)

const maizeByProvince = computed(() => {
  const groups = new Map<string, GrowthCounty[]>()
  for (const row of maizeRows.value) {
    if (!groups.has(row.province)) groups.set(row.province, [])
    groups.get(row.province)!.push(row)
  }
  return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], 'zh-CN'))
})

const factorRows = computed(() => {
  const r = maizeResult.value
  if (!r) return []
  return [
    {
      key: 'gdd',
      label: '积温满足度',
      value: r.scenario.f_gdd,
      hint: `需求 ${r.county.req_gdd} ℃·d（本数据集 4–9 月口径，不作文献绝对值比较）`,
    },
    {
      key: 'water',
      label: '水分满足度',
      value: r.scenario.f_water,
      hint: `作物需水 ${r.scenario.etc.toFixed(0)} mm，供给由有效降水与灌溉合成`,
    },
    {
      key: 'heat',
      label: '热害系数',
      value: r.scenario.f_heat,
      hint: `全季 ≥35℃ 日数按 1/4 折算到抽雄吐丝期`,
    },
  ]
})

async function loadMaize() {
  if (maizeRows.value.length || maizeLoading.value) return
  maizeLoading.value = true
  maizeError.value = ''
  try {
    const data = await fetchGrowthCounties()
    if (!data || !Array.isArray(data.rows)) {
      throw new Error('玉米长势接口未就绪（后端可能仍是旧进程），请重启本地服务后刷新')
    }
    maizeRows.value = data.rows
    maizeMeta.value = data.meta
    const preferred = data.rows.find((r) => r.code === 411623) ?? data.rows[0]
    if (preferred) {
      maizeCode.value = preferred.code
      maizeParams.value = {
        d_temp: 0,
        d_prec_pct: 0,
        d_heat_days: 0,
        irrigation: Math.round(preferred.irr * 100),
      }
    }
  } catch (err) {
    maizeError.value = err instanceof Error ? err.message : '玉米长势基线加载失败'
  } finally {
    maizeLoading.value = false
  }
}

let maizeSeq = 0

async function runMaizeSim() {
  const code = maizeCode.value
  if (!code) return
  const seq = ++maizeSeq
  maizeSimLoading.value = true
  try {
    const result = await postGrowthSimulate({
      county_code: code,
      d_temp: maizeParams.value.d_temp,
      d_prec_pct: maizeParams.value.d_prec_pct,
      d_heat_days: maizeParams.value.d_heat_days,
      irrigation: maizeParams.value.irrigation / 100,
    })
    if (seq === maizeSeq) {
      maizeResult.value = result
      maizeError.value = ''
    }
  } catch (err) {
    if (seq === maizeSeq) {
      maizeError.value = err instanceof Error ? err.message : '情景计算失败'
    }
  } finally {
    if (seq === maizeSeq) maizeSimLoading.value = false
  }
}

const debouncedMaizeSim = debounce(runMaizeSim, 150)

watch(
  [maizeCode, maizeParams],
  () => {
    debouncedMaizeSim()
  },
  { deep: true, flush: 'post' },
)

// 切县时回到该县基线，避免把上一个县的灌溉率带过去。
watch(maizeCode, (code) => {
  const row = maizeRows.value.find((r) => r.code === code)
  if (!row) return
  maizeParams.value = {
    d_temp: 0,
    d_prec_pct: 0,
    d_heat_days: 0,
    irrigation: Math.round(row.irr * 100),
  }
  maizeResult.value = null
})

watch(activeTab, async (tab) => {
  if (tab === 'maize') {
    loadMaize()
    return
  }
  // v-show 隐藏期间 ECharts 容器尺寸会变成 0，切回来必须 resize + 重绘。
  await nextTick()
  gaugeBase?.resize()
  gaugeSim?.resize()
  contribChart?.resize()
  rerender()
})

function resetMaize() {
  const row = maizeCounty.value
  maizeParams.value = {
    d_temp: 0,
    d_prec_pct: 0,
    d_heat_days: 0,
    irrigation: row ? Math.round(row.irr * 100) : 60,
  }
}

function pctOfGrowth(val: number, def: GrowthSliderDef): number {
  return ((val - def.min) / (def.max - def.min)) * 100
}

function growthBaselineValue(def: GrowthSliderDef): number {
  if (def.key === 'irrigation') return (maizeCounty.value?.irr ?? 0.6) * 100
  return 0
}

function fmtGrowth(val: number, def: GrowthSliderDef): string {
  if (def.key === 'd_temp') return `${val > 0 ? '+' : ''}${val.toFixed(1)}`
  if (def.key === 'irrigation') return val.toFixed(0)
  return `${val > 0 ? '+' : ''}${val.toFixed(0)}`
}

function factorClass(val: number): string {
  if (val >= 0.9) return 'good'
  if (val >= 0.75) return 'warn'
  return 'bad'
}

onMounted(() => {
  if (gaugeBaseEl.value) gaugeBase = echarts.init(gaugeBaseEl.value, undefined, { renderer: 'canvas' })
  if (gaugeSimEl.value) gaugeSim = echarts.init(gaugeSimEl.value, undefined, { renderer: 'canvas' })
  if (contribEl.value) contribChart = echarts.init(contribEl.value, undefined, { renderer: 'canvas' })
  rerender()
  resizeHandler = () => {
    gaugeBase?.resize()
    gaugeSim?.resize()
    contribChart?.resize()
  }
  window.addEventListener('resize', resizeHandler)
})

onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  gaugeBase?.dispose()
  gaugeSim?.dispose()
  contribChart?.dispose()
})
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M03 · COUNTERFACTUAL SCENARIO SIMULATION</div>
      <h2>参数情景模拟</h2>
      <p class="lead">
        「风险情景」调节灌溉率、洪涝占比、日照、气温、SPEI,查看风险变化;
        「玉米长势」按区域推演温度、降水、热害与灌溉对玉米相对长势的影响。
      </p>
      <div class="tabs" role="tablist" aria-label="M03 情景模拟视图">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'risk' }"
          type="button"
          role="tab"
          :aria-selected="activeTab === 'risk'"
          @click="activeTab = 'risk'"
        >
          风险情景
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'maize' }"
          type="button"
          role="tab"
          :aria-selected="activeTab === 'maize'"
          @click="activeTab = 'maize'"
        >
          玉米长势
        </button>
      </div>
    </header>

    <div v-show="activeTab === 'risk'" class="grid">
      <!-- 左：省份 + sliders -->
      <aside class="left-col" aria-label="情景参数控制区">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="num">M03-A</div>
              <h3 id="scenario-target-heading">选择省份</h3>
            </div>
            <button
              class="reset-btn"
              type="button"
              aria-label="将所有干预参数重置回省份基线值"
              @click="resetToBaseline"
            >↺ 重置基线</button>
          </div>
          <!-- a11y SC 1.3.1 / 4.1.2:select 加 aria-label 显式关联 -->
          <label class="sr-only" for="province-select-scenario">目标省份选择器</label>
          <select
            id="province-select-scenario"
            v-model.number="selectedIdx"
            class="province-select"
            aria-labelledby="scenario-target-heading"
          >
            <option v-for="(p, i) in PROVINCES_PROFILE" :key="p.name" :value="i">
              {{ p.name }} · {{ p.type }}
            </option>
          </select>
          <div class="baseline-info">
            <span>基线 Y</span>
            <span class="v">{{ selected.y.toFixed(4) }}</span>
            <span class="dot" aria-hidden="true">·</span>
            <span>{{ selected.type }}</span>
          </div>
        </div>

        <div class="card sliders-card">
          <div class="card-head">
            <div>
              <div class="num">M03-B</div>
              <h3 id="controls-heading">5 维干预参数</h3>
            </div>
          </div>
          <div class="sliders" role="group" aria-labelledby="controls-heading">
            <div v-for="def in SLIDERS" :key="def.key" class="slider-card">
              <div class="slider-head">
                <span class="slider-name">
                  <span class="icon" :class="def.iconCls" aria-hidden="true">{{ def.icon }}</span>
                  {{ def.label }}
                  <span class="key" aria-hidden="true">{{ def.key.toUpperCase() }}</span>
                </span>
                <span class="slider-value">
                  {{ fmtVal(def.key, params[def.key]) }}<span class="unit">{{ def.unit }}</span>
                </span>
              </div>
              <div class="slider-track-wrap">
                <div class="slider-track" aria-hidden="true">
                  <div class="slider-baseline" :style="{ left: pctOf(baseline[def.key], def) + '%' }"></div>
                  <div class="slider-fill" :style="{ width: pctOf(params[def.key], def) + '%' }"></div>
                  <div class="slider-thumb" :style="{ left: pctOf(params[def.key], def) + '%' }"></div>
                </div>
                <!-- a11y SC 1.3.1 + SC 4.1.2:每个滑块 aria-label/valuemin/max/now/valuetext -->
                <input
                  v-model.number="params[def.key]"
                  type="range"
                  class="native-range"
                  :min="def.min"
                  :max="def.max"
                  :step="def.step"
                  :aria-label="`${def.label},最小值 ${def.min}${def.unit},最大值 ${def.max}${def.unit},${def.hint}`"
                  :aria-valuemin="def.min"
                  :aria-valuemax="def.max"
                  :aria-valuenow="params[def.key]"
                  :aria-valuetext="`${fmtVal(def.key, params[def.key])}${def.unit}`"
                />
              </div>
              <div class="slider-scale">
                <span>{{ def.min }}</span>
                <span class="hint">{{ def.hint }}</span>
                <span>{{ def.max }}</span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 右：双 gauge + delta + 贡献度 -->
      <section class="right-col" aria-label="情景模拟结果区">
        <div class="gauges">
          <div class="card gauge-card">
            <div class="card-head">
              <div>
                <div class="num">M03-C</div>
                <h3>基线风险 Y</h3>
              </div>
            </div>
            <!-- a11y SC 1.1.1:gauge canvas 文本替代 -->
            <div
              ref="gaugeBaseEl"
              class="gauge-canvas"
              role="img"
              :aria-label="`基线风险 Y 仪表盘,当前值 ${selected.y.toFixed(4)}`"
              tabindex="0"
            ></div>
          </div>
          <div class="card gauge-card">
            <div class="card-head">
              <div>
                <div class="num">M03-D</div>
                <h3>模拟风险 Y</h3>
              </div>
              <div class="sim-head-right">
                <span
                  v-if="isLoadingBackend"
                  class="backend-tag loading"
                  role="status"
                  aria-live="polite"
                  aria-label="正在计算"
                >
                  <span class="backend-spinner" aria-hidden="true"></span>
                </span>
                <!-- a11y SC 1.4.1:WORSE/BETTER 不只靠色,文字 + 上下箭头双通道 -->
                <span
                  class="sim-tag"
                  :class="{ worse: isWorse, better: !isWorse }"
                  :aria-label="isWorse ? '风险上升' : '风险下降'"
                >
                  <span aria-hidden="true">{{ isWorse ? '▲ ' : '▼ ' }}</span>{{ isWorse ? '风险上升' : '风险下降' }}
                </span>
              </div>
            </div>
            <div
              ref="gaugeSimEl"
              class="gauge-canvas"
              role="img"
              :aria-label="`模拟风险 Y 仪表盘,当前值 ${simRisk.toFixed(4)},较基线${isWorse ? '上升' : '下降'} ${Math.abs(deltaPct).toFixed(1)}%`"
              tabindex="0"
            ></div>
          </div>
        </div>

        <!-- a11y SC 4.1.3:delta-card 内容更新时通过 aria-live 朗读 -->
        <div
          class="card delta-card"
          :class="{ worse: isWorse, better: !isWorse }"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <div class="delta-head">
            <span class="num">M03-E</span>
            <span class="label">基线 → 模拟</span>
          </div>
          <div class="delta-body">
            <div class="delta-main">
              <span class="arrow" aria-hidden="true">{{ isWorse ? '▲' : '▼' }}</span>
              <span class="abs">{{ Math.abs(delta).toFixed(4) }}</span>
            </div>
            <div class="delta-sub">
              较基线 <span class="pct">{{ isWorse ? '+' : '−' }}{{ Math.abs(deltaPct).toFixed(1) }}%</span>
              <span class="dot" aria-hidden="true">·</span>
              {{ isWorse ? '风险上升,建议复核干预方向' : '风险下降,韧性提升' }}
            </div>
          </div>
        </div>

        <div class="card contrib-card">
          <div class="card-head">
            <div>
              <div class="num">M03-F</div>
              <h3>各参数对风险的边际贡献</h3>
            </div>
            <div class="contrib-legend">
              <span><span class="swatch up" aria-hidden="true"></span>推升风险</span>
              <span><span class="swatch dn" aria-hidden="true"></span>降低风险</span>
            </div>
          </div>
          <!-- a11y SC 1.1.1:贡献度图文本替代 -->
          <div
            ref="contribEl"
            class="contrib-canvas"
            role="img"
            aria-label="各干预参数对风险的边际贡献条形图:正值(赭石色)推高风险,负值(绿色)降低风险,按绝对值由大到小排序"
            tabindex="0"
          ></div>
        </div>
      </section>
    </div>

    <!-- 玉米长势：与风险情景并列的第二个页签 -->
    <div v-if="activeTab === 'maize'" class="grid">
      <aside class="left-col" aria-label="玉米长势参数控制区">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="num">M03-M1</div>
              <h3 id="maize-county-heading">选择玉米主产县</h3>
            </div>
            <button
              class="reset-btn"
              type="button"
              aria-label="将玉米长势情景参数重置回该县基线"
              @click="resetMaize"
            >↺ 重置基线</button>
          </div>
          <label class="sr-only" for="maize-county-select">玉米主产县选择器</label>
          <select
            id="maize-county-select"
            v-model.number="maizeCode"
            class="province-select"
            :disabled="maizeLoading"
            aria-labelledby="maize-county-heading"
          >
            <option v-if="maizeLoading" :value="null">加载中…</option>
            <optgroup v-for="group in maizeByProvince" :key="group[0]" :label="group[0]">
              <option v-for="row in group[1]" :key="row.code" :value="row.code">
                {{ row.name }} · {{ row.city }}
              </option>
            </optgroup>
          </select>
          <div v-if="maizeCounty" class="baseline-info">
            <span>{{ maizeCounty.zone === 'NE' ? '东北春玉米' : maizeCounty.zone === 'HHH' ? '黄淮海夏玉米' : '西南春玉米' }}</span>
            <span class="dot" aria-hidden="true">·</span>
            <span>GDD {{ maizeCounty.gdd.toFixed(0) }}</span>
            <span class="dot" aria-hidden="true">·</span>
            <span>降水 {{ maizeCounty.ppt.toFixed(0) }} mm</span>
          </div>
          <p v-if="maizeError" class="maize-error" role="alert">{{ maizeError }}</p>
        </div>

        <div class="card sliders-card">
          <div class="card-head">
            <div>
              <div class="num">M03-M2</div>
              <h3 id="maize-controls-heading">作物情景参数</h3>
            </div>
          </div>
          <div class="sliders" role="group" aria-labelledby="maize-controls-heading">
            <div v-for="def in GROWTH_SLIDERS" :key="def.key" class="slider-card">
              <div class="slider-head">
                <span class="slider-name">
                  <span class="icon" :class="def.iconCls" aria-hidden="true">{{ def.icon }}</span>
                  {{ def.label }}
                  <span class="key" aria-hidden="true">{{ def.key.toUpperCase() }}</span>
                </span>
                <span class="slider-value">
                  {{ fmtGrowth(maizeParams[def.key], def) }}<span class="unit">{{ def.unit }}</span>
                </span>
              </div>
              <div class="slider-track-wrap">
                <div class="slider-track" aria-hidden="true">
                  <div class="slider-baseline" :style="{ left: pctOfGrowth(growthBaselineValue(def), def) + '%' }"></div>
                  <div class="slider-fill" :style="{ width: pctOfGrowth(maizeParams[def.key], def) + '%' }"></div>
                  <div class="slider-thumb" :style="{ left: pctOfGrowth(maizeParams[def.key], def) + '%' }"></div>
                </div>
                <input
                  v-model.number="maizeParams[def.key]"
                  type="range"
                  class="native-range"
                  :min="def.min"
                  :max="def.max"
                  :step="def.step"
                  :aria-label="`${def.label},最小值 ${def.min}${def.unit},最大值 ${def.max}${def.unit},${def.hint}`"
                  :aria-valuemin="def.min"
                  :aria-valuemax="def.max"
                  :aria-valuenow="maizeParams[def.key]"
                  :aria-valuetext="`${fmtGrowth(maizeParams[def.key], def)}${def.unit}`"
                />
              </div>
              <div class="slider-scale">
                <span>{{ def.min }}</span>
                <span class="hint">{{ def.hint }}</span>
                <span>{{ def.max }}</span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <section class="right-col" aria-label="玉米长势结果区">
        <div v-if="maizeResult" class="card maize-result-card" aria-live="polite">
          <div class="card-head">
            <div>
              <div class="num">M03-M3</div>
              <h3>相对长势指数 · {{ maizeResult.county.name }}</h3>
            </div>
            <div class="sim-head-right">
              <span v-if="maizeSimLoading" class="backend-tag loading" role="status" aria-label="正在计算">
                <span class="backend-spinner" aria-hidden="true"></span>
              </span>
              <span
                class="sim-tag"
                :class="maizeResult.delta_pct >= 0 ? 'better' : 'worse'"
              >{{ maizeResult.delta_pct >= 0 ? '+' : '' }}{{ maizeResult.delta_pct.toFixed(1) }}%</span>
            </div>
          </div>
          <div class="gsi-wrap">
            <div class="gsi-value" :class="{ down: maizeResult.delta_pct < 0 }">
              {{ maizeResult.gsi.toFixed(1) }}
            </div>
            <div class="gsi-scale">
              <span>常年 = 100</span>
              <span>主产区第 {{ maizeResult.percentile }} 分位</span>
            </div>
          </div>
          <p class="gsi-note">{{ maizeResult.interpretation }}</p>
          <p class="gsi-meta">
            {{ maizeResult.metric_note }}
            <span v-if="maizeMeta" class="dot" aria-hidden="true">·</span>
            <span v-if="maizeMeta">{{ maizeMeta.county_count }} 县 · {{ maizeMeta.years[0] }}–{{ maizeMeta.years[1] }}</span>
          </p>
        </div>
        <div v-else class="card maize-empty" role="status">
          {{ maizeLoading ? '正在加载玉米主产县…' : '选择县后显示长势结果' }}
        </div>

        <div v-if="maizeResult" class="card">
          <div class="card-head">
            <div>
              <div class="num">M03-M4</div>
              <h3>限制因子分解</h3>
            </div>
            <span class="factor-chip">主限制：{{ maizeResult.limiting_label }}</span>
          </div>
          <div class="factor-list">
            <div v-for="f in factorRows" :key="f.key" class="factor-row">
              <div class="factor-head">
                <span>{{ f.label }}</span>
                <span class="factor-val">{{ (f.value * 100).toFixed(0) }}%</span>
              </div>
              <div class="factor-track">
                <div
                  class="factor-fill"
                  :class="factorClass(f.value)"
                  :style="{ width: Math.max(4, f.value * 100) + '%' }"
                ></div>
              </div>
              <p class="factor-hint">{{ f.hint }}</p>
            </div>
          </div>
        </div>

        <div v-if="maizeResult" class="card">
          <div class="card-head">
            <div>
              <div class="num">M03-M5</div>
              <h3>基线 → 情景</h3>
            </div>
            <span class="factor-chip">{{ maizeResult.county.zone_name }} · 播期 {{ maizeResult.county.sowing }}</span>
          </div>
          <table class="cmp-table">
            <thead>
              <tr><th scope="col">指标</th><th scope="col">常年</th><th scope="col">情景</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>≥10℃ 积温</td>
                <td>{{ maizeResult.baseline.gdd.toFixed(0) }}</td>
                <td>{{ maizeResult.scenario.gdd.toFixed(0) }}</td>
              </tr>
              <tr>
                <td>生长季降水</td>
                <td>{{ maizeResult.baseline.ppt.toFixed(0) }} mm</td>
                <td>{{ maizeResult.scenario.ppt.toFixed(0) }} mm</td>
              </tr>
              <tr>
                <td>作物需水 ETc</td>
                <td>{{ maizeResult.baseline.etc.toFixed(0) }} mm</td>
                <td>{{ maizeResult.scenario.etc.toFixed(0) }} mm</td>
              </tr>
              <tr>
                <td>≥35℃ 高温日</td>
                <td>{{ maizeResult.baseline.heat_days.toFixed(0) }}</td>
                <td>{{ maizeResult.scenario.heat_days.toFixed(0) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1480px; margin: 0 auto; }

.page-head { margin-bottom: 24px; }
.eyebrow { font-family: var(--font-mono); font-size: 10px; color: var(--green); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 8px; }
.page-head h2 { font-family: var(--font-serif); font-size: 26px; font-weight: 600; margin-bottom: 6px; }
.lead { font-size: 13px; color: var(--text-2); max-width: 920px; line-height: 1.7; }

.grid {
  display: grid;
  grid-template-columns: minmax(360px, 1fr) minmax(0, 1.3fr);
  gap: 20px;
}
/* 平板竖屏:左侧控制面板 360px 硬下限会把右侧结果区挤到很窄,改上下堆叠 */
@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
}

.left-col, .right-col { display: flex; flex-direction: column; gap: 16px; }

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-head .num { font-family: var(--font-mono); font-size: 9px; color: var(--text-3); letter-spacing: 1px; margin-bottom: 2px; }
.card-head h3 { font-family: var(--font-serif); font-size: 14px; font-weight: 600; }

.reset-btn {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 4px 10px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  color: var(--text-2);
  cursor: pointer;
}
.reset-btn:hover { color: var(--green-bright); border-color: var(--green); }

.province-select {
  width: 100%;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--text);
  padding: 10px 12px;
  font-size: 12px;
  cursor: pointer;
  appearance: none;
  margin-bottom: 10px;
}
/* a11y SC 2.4.11 Focus Appearance:替代 outline:none,2px green-bright + offset */
.province-select:focus { border-color: var(--green); }
.province-select:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
  border-color: var(--green-bright);
}

.baseline-info {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
  display: flex;
  gap: 6px;
  align-items: center;
}
.baseline-info .v { color: var(--green-bright); font-weight: 600; }
.baseline-info .dot { color: var(--border-strong); }

/* ============ sliders ============ */
.sliders-card .sliders { display: flex; flex-direction: column; gap: 12px; max-height: 560px; overflow-y: auto; padding-right: 4px; }
.sliders::-webkit-scrollbar { width: 4px; }
.sliders::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 2px; }

.slider-card {
  background: var(--bg-elev);
  border-radius: var(--r-md);
  padding: 12px 14px;
  border: 1px solid transparent;
}

.slider-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.slider-name { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); font-weight: 500; }
.slider-name .key { font-family: var(--font-mono); color: var(--text-3); font-size: 9px; letter-spacing: 0.5px; }
.slider-name .icon {
  width: 26px; height: 26px;
  border-radius: 6px;
  font-family: var(--font-serif); font-weight: 600; font-size: 11px;
  display: flex; align-items: center; justify-content: center;
}
.slider-name .icon.green { background: rgba(160, 183, 133, 0.15); color: var(--green-bright); }
.slider-name .icon.red { background: rgba(184, 111, 77, 0.15); color: var(--risk-4); }
.slider-name .icon.amber { background: rgba(230, 182, 85, 0.15); color: var(--amber); }
.slider-name .icon.purple { background: rgba(180, 157, 216, 0.15); color: var(--purple); }

.slider-value {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--green-bright);
}
.slider-value .unit { font-size: 10px; margin-left: 2px; color: var(--text-3); font-weight: 400; }

.slider-track-wrap { position: relative; padding: 8px 0; }
.slider-track {
  height: 4px;
  background: var(--bg);
  border-radius: 2px;
  position: relative;
}
.slider-baseline {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 10px;
  background: var(--text-3);
  border-radius: 1px;
  transform: translateX(-1px);
}
.slider-fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, var(--green-deep), var(--green-bright));
  border-radius: 2px;
}
.slider-thumb {
  position: absolute;
  top: 50%;
  width: 12px; height: 12px;
  background: var(--bg);
  border: 2px solid var(--green-bright);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.native-range {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  opacity: 0; cursor: pointer; z-index: 2;
}
/* a11y SC 2.4.11:opacity:0 隐了原生 focus ring,
   focus 时给父 wrapper 加可见 ring 等价反馈 */
.slider-track-wrap:focus-within .slider-track {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
  border-radius: 4px;
}
.slider-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
}
.slider-scale .hint { color: var(--text-2); }

/* ============ gauges ============ */
.gauges { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.gauge-card { display: flex; flex-direction: column; }
.gauge-canvas { height: 220px; }

.sim-head-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.sim-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 3px 10px;
  border-radius: 10px;
  letter-spacing: 0.5px;
}
.sim-tag.worse { background: rgba(184, 111, 77, 0.12); color: var(--risk-4); }
.sim-tag.better { background: rgba(160, 183, 133, 0.12); color: var(--green-bright); }

.backend-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 8px;
}
.backend-tag.loading { background: rgba(230, 182, 85, 0.10); }
.backend-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(230, 182, 85, 0.25);
  border-top-color: var(--amber);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ============ delta ============ */
.delta-card { padding: 18px 20px; }
.delta-card.worse { border-left: 4px solid var(--risk-4); }
.delta-card.better { border-left: 4px solid var(--green-bright); }
.delta-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 10px;
}
.delta-head .num { font-family: var(--font-mono); font-size: 9px; color: var(--text-3); letter-spacing: 1px; }
.delta-head .label { font-family: var(--font-mono); font-size: 10px; color: var(--text-2); }
.delta-body { display: flex; flex-direction: column; gap: 6px; }
.delta-main {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-family: var(--font-mono);
}
.delta-main .arrow { font-size: 18px; }
.delta-main .abs { font-size: 30px; font-weight: 700; line-height: 1; }
.delta-card.worse .delta-main { color: var(--risk-4); }
.delta-card.better .delta-main { color: var(--green-bright); }
.delta-sub {
  font-size: 12px;
  color: var(--text-2);
}
.delta-sub .pct {
  font-family: var(--font-mono);
  font-weight: 600;
  margin: 0 4px;
}
.delta-card.worse .delta-sub .pct { color: var(--risk-4); }
.delta-card.better .delta-sub .pct { color: var(--green-bright); }
.delta-sub .dot { color: var(--border-strong); margin: 0 6px; }

/* ============ contrib ============ */
.contrib-card { display: flex; flex-direction: column; min-height: 280px; }
.contrib-legend {
  display: flex;
  gap: 12px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-2);
}
.contrib-legend .swatch {
  display: inline-block;
  width: 10px; height: 3px;
  margin-right: 4px;
  border-radius: 1px;
  vertical-align: middle;
}
.contrib-legend .swatch.up { background: var(--risk-4); }
.contrib-legend .swatch.dn { background: var(--green); }
.contrib-canvas { flex: 1; min-height: 220px; }

/* ============ M03 页签 ============ */
.tabs {
  display: inline-flex;
  gap: 4px;
  margin-top: 14px;
  padding: 3px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 999px;
}
.tab-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.5px;
  padding: 6px 16px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active {
  background: var(--green-deep);
  color: var(--bg);
  font-weight: 600;
}
.tab-btn:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

/* ============ 玉米长势 ============ */
.maize-result-card { border-left: 4px solid var(--green); }
.gsi-wrap {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 4px 12px;
}
.gsi-value {
  font-family: var(--font-mono);
  font-size: 64px;
  font-weight: 700;
  line-height: 0.95;
  color: var(--green-bright);
  letter-spacing: -2px;
}
.gsi-value.down { color: var(--risk-4); }
.gsi-scale {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
}
.gsi-note {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
  padding: 12px 4px 0;
  border-top: 1px solid var(--border);
}
.gsi-meta {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-3);
  line-height: 1.6;
}
.gsi-meta .dot { margin: 0 6px; color: var(--border-strong); }

.factor-chip {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-2);
  padding: 3px 9px;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
}
.factor-list { display: flex; flex-direction: column; gap: 14px; }
.factor-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 12px;
  color: var(--text);
  margin-bottom: 6px;
}
.factor-val {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-2);
}
.factor-track {
  height: 8px;
  background: var(--bg);
  border-radius: 4px;
  overflow: hidden;
}
.factor-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 180ms ease;
}
.factor-fill.good { background: linear-gradient(90deg, var(--green-deep), var(--green-bright)); }
.factor-fill.warn { background: linear-gradient(90deg, #8a6a2d, var(--amber)); }
.factor-fill.bad { background: linear-gradient(90deg, #7a3f2a, var(--risk-4)); }
.factor-hint {
  margin-top: 5px;
  font-size: 10px;
  color: var(--text-3);
  line-height: 1.5;
}

.cmp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.cmp-table th,
.cmp-table td {
  padding: 8px 6px;
  text-align: right;
  border-bottom: 1px solid var(--border);
}
.cmp-table th:first-child,
.cmp-table td:first-child { text-align: left; color: var(--text-2); }
.cmp-table th {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
  color: var(--text-3);
}
.cmp-table td {
  font-family: var(--font-mono);
  color: var(--text);
}
.cmp-table tr:last-child td { border-bottom: 0; }

.maize-empty {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: 12px;
}
.maize-error {
  margin-top: 10px;
  font-size: 11px;
  color: var(--risk-4);
  line-height: 1.6;
}

</style>
