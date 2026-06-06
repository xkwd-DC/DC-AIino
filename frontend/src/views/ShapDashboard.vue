<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { getCSSVar } from '@/data/mockProvinces'
import { postPredict, type ShapContrib, type ShapNormalized } from '@/api/predict'
import { fetchShapSubset, type ShapSubset, type SubsetKey } from '@/api/shap'
import { useProvinceStore } from '@/stores/useProvinceStore'
import { storeToRefs } from 'pinia'
// a11y: ECharts 动画绕过 CSS prefers-reduced-motion,JS 探测后传 0
import { motionDuration } from '@/data/a11y'

// 11 维特征中文 ↔ 英文短码映射。仅 schema/lookup 用途,顺序不再决定渲染顺序,
// 渲染顺序由 backend 返回的 shap_normalized(按 importance 降序)决定。
const FEATURE_EN_LOOKUP: Record<string, string> = {
  '灌溉率': 'Irr',
  '洪涝占比': 'Flood_R',
  '日照时数': 'Sun',
  '平均气温': 'Temp',
  'SPEI 干旱指数': 'SPEI',
  '降水量': 'Prec',
  '农机总动力': 'Mech',
  '化肥施用量': 'Fert',
  '旱灾面积': 'Drou_A',
  '水灾面积': 'Flood_A',
  'NDVI 异常': 'NDVI',
}

interface Feature {
  name: string
  en: string
  shap: number          // 用于 bar chart 渲染的 importance(0-1, 已 abs 归一)
  rawAbs: number        // 原始 abs 贡献, tooltip 展示
  dir: 'green' | 'red'
  hasValue: boolean     // 始终 true(全 11 维都有真值);保留字段以兼容老模板
}

// ── 后端 SHAP 状态 ────────────────────────────────────────────────────────
// 优先用归一化 11 维全量;若后端老版本不返 shap_normalized,从 shap_top 回退合成。
const backendNormalized = ref<ShapNormalized[] | null>(null)
const backendContribs = ref<ShapContrib[] | null>(null)
const isLoadingShap = ref(false)
const shapError = ref<string | null>(null)

const provinceStore = useProvinceStore()
const {
  selectedIdx,
  selected: selectedProvince,
  profiles,
  isLoading: storeLoading,
  source: storeSource,
} = storeToRefs(provinceStore)

/** 用 shap_normalized(11 维归一化) 直接生成 Feature[]。已按 importance 降序。 */
function fromNormalized(items: ShapNormalized[]): Feature[] {
  return items.map((it) => ({
    name: it.feature,
    en: FEATURE_EN_LOOKUP[it.feature] ?? '',
    shap: it.importance,
    rawAbs: it.raw_abs,
    dir: it.direction === 'harm' ? 'red' : 'green',
    hasValue: true,
  }))
}

/** 老后端 fallback:从 shap_top 现场合成归一化 importance。
 *  shap_top 可能只 5 维,合成后仍 5 维;视觉饱满度依赖后端升级。 */
function fromContribsFallback(contribs: ShapContrib[]): Feature[] {
  const absVals = contribs.map((c) => Math.abs(c.value))
  const total = absVals.reduce((a, b) => a + b, 0) || 1
  return contribs
    .map((c, i) => ({
      name: c.feature,
      en: FEATURE_EN_LOOKUP[c.feature] ?? '',
      shap: absVals[i] / total,
      rawAbs: Math.abs(c.value),
      dir: c.direction === 'harm' ? ('red' as const) : ('green' as const),
      hasValue: true,
    }))
    .sort((a, b) => b.shap - a.shap)
}

/** 当前 11 维特征数据。优先 normalized,其次 contribs fallback,否则空数组。 */
const FEATURES_ALL = computed<Feature[]>(() => {
  if (backendNormalized.value) return fromNormalized(backendNormalized.value)
  if (backendContribs.value) return fromContribsFallback(backendContribs.value)
  return []
})

const shapDataSource = computed<'loading' | 'error' | 'model' | 'idle'>(() => {
  if (isLoadingShap.value) return 'loading'
  if (shapError.value) return 'error'
  if (backendNormalized.value || backendContribs.value) return 'model'
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
    backendNormalized.value = data.shap_normalized ?? null
    backendContribs.value = data.shap_top
  } catch (e: unknown) {
    shapError.value = e instanceof Error ? e.message : 'network error'
    backendNormalized.value = null
    backendContribs.value = null
  } finally {
    isLoadingShap.value = false
  }
}

// 省份切换时:
//   1. 自动切回 'single' 模式 — 让 bar chart 立刻响应新省份(用户视角"切了有用")
//   2. 重新拉单省 SHAP(waterfall + bar 共用)
// 注意:如果用户当前正看 subset 模式(如"全样本"), 省份切换会强制跳回 single,
// 这是产品决策——因为 subset 跨省聚合本来就不依赖单省选择。
watch(selectedProvince, () => {
  if (selectedProvince.value?.name) {
    backendNormalized.value = null
    backendContribs.value = null
    shapError.value = null
    currentSubsetKey.value = 'single'
    fetchShapData()
  }
})

// ── M02-A SUBSET 子集聚合 SHAP(全局重要性 bar chart 数据源)──────────────
// 与 M02-B waterfall(单省 SHAP)正交并存:
//   - 单省 dropdown(M02-0)→ 控制 M02-B 单样本分解
//   - 5-button SUBSET → 控制 M02-A 全局 bar chart
//       · 'single': 当前 TARGET 省份单省 SHAP(来源 /api/predict shap_normalized)
//       · 其余 4 个: subset 内所有省份 abs 贡献跨省聚合
// 聚合后 sign 失真,direction 一律 'neutral',不强调推/降方向。
// 'single' 模式保留 harm/protect direction(单省单样本仍有意义)。
const SUBSETS: { key: SubsetKey; label: string }[] = [
  { key: 'single', label: '当前省份' },  // 标签运行时拼接省名
  { key: 'all',    label: '全样本' },
  { key: 'north',  label: '北方' },
  { key: 'south',  label: '南方' },
  { key: 'major',  label: '主产区' },
]

const currentSubsetKey = ref<SubsetKey>('single')
const subsetData = ref<ShapSubset | null>(null)
const subsetLoading = ref(false)
const subsetError = ref<string | null>(null)

async function fetchSubset(key: SubsetKey): Promise<void> {
  // 'single' 模式不调 backend subset endpoint, 数据源来自 /api/predict 的
  // shap_normalized(由 fetchShapData 维护)。清空 subsetData 让 features
  // computed fallback 到 FEATURES_ALL(单省单样本归因)。
  if (key === 'single') {
    subsetData.value = null
    subsetError.value = null
    subsetLoading.value = false
    // 若单省 SHAP 还没拿到(初次进页 / 错误后重试), 触发 fetchShapData
    if (!backendNormalized.value && !backendContribs.value && !isLoadingShap.value) {
      void fetchShapData()
    }
    return
  }
  subsetLoading.value = true
  subsetError.value = null
  try {
    subsetData.value = await fetchShapSubset(key)
  } catch (e: unknown) {
    subsetError.value = e instanceof Error ? e.message : 'network error'
    subsetData.value = null
  } finally {
    subsetLoading.value = false
  }
}

watch(currentSubsetKey, (key) => {
  void fetchSubset(key)
})

/** 从 subset 聚合结果生成 bar chart 用 Feature[]。聚合后 direction='neutral',
 *  渲染时按"中性绿"色阶展示(不偏 harm/protect)。 */
function fromSubset(subset: ShapSubset): Feature[] {
  return subset.features.map((f) => ({
    name: f.feature,
    en: FEATURE_EN_LOOKUP[f.feature] ?? '',
    shap: f.importance,
    rawAbs: f.mean_abs,
    // direction 在聚合后失真;用 'green' 作为中性色,避免误读为某方向因子。
    dir: 'green' as const,
    hasValue: true,
  }))
}

/** 当前 M02-A bar chart 用的 11 维特征数据。
 *  - 'single' 模式: 用单省 /api/predict 的 shap_normalized(FEATURES_ALL),
 *    让 TARGET 省份切换可见地刷新 bar(harm/protect 方向有效)
 *  - subset 模式: 用 fetchShapSubset 跨省聚合(direction 为 neutral)
 *  - subset loading / error 时 fallback 到 FEATURES_ALL,避免空白闪烁 */
const features = computed<Feature[]>(() => {
  if (currentSubsetKey.value === 'single') return FEATURES_ALL.value
  if (subsetData.value) return fromSubset(subsetData.value)
  return FEATURES_ALL.value
})

/** Bar chart subtitle 文案 — single 模式显示当前省名,subset 模式显示聚合 N 省。 */
const subsetSubtitle = computed<string>(() => {
  if (currentSubsetKey.value === 'single') {
    const prov = selectedProvince.value?.name
    if (isLoadingShap.value) return '正在计算单省 SHAP...'
    if (shapError.value) return '单省 SHAP 拉取失败'
    if (prov) return `省内因子相对重要性 · ${prov}`
    return '省内因子相对重要性'
  }
  if (subsetLoading.value) return '正在聚合子集...'
  if (subsetError.value) return '子集聚合失败,展示单省'
  if (subsetData.value) {
    return `聚合 ${subsetData.value.province_count} 省 mean(|SHAP|)`
  }
  return ''
})

// ── M02-B 省内因子带向贡献(signed marginal contribution)─────────────────
// 取当前省份单省 SHAP(FEATURES_ALL)的「有符号」边际贡献:
//   正值(red) = 该因子在本省取值相对跨省均值「推升」风险
//   负值(green)= 「降低」风险
// 注:本页输入恒为省份 baseline → 预测≈基线,baseline→f(x) 累计 waterfall 无意义,
// 且单特征扰动 contribs 非可加 SHAP;故改为直接展示各因子带符号贡献,
// 切换省份即随真值刷新(修复"切省归因不变")。
interface ContribBar {
  name: string
  en: string
  value: number          // signed:>0 推升风险(red) / <0 降低风险(green)
}

const CONTRIB_TOP_N = 8

const contribBars = computed<ContribBar[]>(() => {
  const f = FEATURES_ALL.value
  if (f.length === 0) return []
  return f.slice(0, CONTRIB_TOP_N).map((x) => ({
    name: x.name,
    en: x.en,
    value: x.dir === 'red' ? x.rawAbs : -x.rawAbs,
  }))
})

/** 头部 readout:本省最强带向因子(名称 + 方向)。 */
const contribHeadline = computed<string>(() => {
  const f = FEATURES_ALL.value
  if (f.length === 0) return '—'
  return `${f[0].name} · ${f[0].dir === 'red' ? '推升' : '降低'}风险`
})

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

// 蜂群分布:用当前省份单省 SHAP 的 Top-5 因子驱动 —
//   · 每个因子的「方向 + 相对强度」来自真实 contribs(切省即变)
//   · 样本级 SHAP endpoint 未开,故点云为围绕真值的「示意分布」(spread 为示意)
// seed 由本省 Top-5 真值派生 → 不同省份散点形态不同。
function generateBeeswarmPoints(): { features: string[]; points: BeePoint[] } {
  const top5 = FEATURES_ALL.value.slice(0, 5)
  if (top5.length === 0) return { features: [], points: [] }
  const maxAbs = top5.reduce((m, x) => Math.max(m, x.rawAbs), 0) || 0.001
  const seedBase =
    (Math.floor(top5.reduce((s, x, i) => s + x.rawAbs * 1e6 * (i + 1), 0)) % 90000) + 17
  const points: BeePoint[] = []
  top5.forEach((ft, fi) => {
    const sign = ft.dir === 'red' ? 1 : -1
    const center = sign * (ft.rawAbs / maxAbs) * 0.42      // 真实带向贡献映射到 [-0.42, 0.42]
    const spread = 0.04 + (ft.rawAbs / maxAbs) * 0.1
    const rng = seededRandom(seedBase + fi * 1000 + 97)
    const n = 56 + Math.floor(rng() * 16)
    for (let i = 0; i < n; i++) {
      const u = rng() || 0.0001
      const v = rng() || 0.0001
      const gauss = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
      const shap = center + gauss * spread
      const rawNorm = Math.max(0, Math.min(1, 0.5 + sign * (shap - center) * 3 + (rng() - 0.5) * 0.3))
      const jitter = (rng() - 0.5) * 0.62
      points.push({ fi, shap, raw: shap, rawNorm, yPos: fi + jitter })
    }
  })
  return { features: top5.map((x) => x.name), points }
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
  // xAxis 自适应:最大 importance × 1.15(给 label 留 padding;原 0.55 写死是为 mock 大数字)
  const maxImportance = f.reduce((m, x) => Math.max(m, x.shap), 0)
  const xMax = maxImportance > 0 ? +(maxImportance * 1.15).toFixed(3) : 1
  importanceChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 100, right: 70, top: 14, bottom: 28 },
      tooltip: {
        trigger: 'item',
        backgroundColor: getCSSVar('--bg-elev'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 12 },
        formatter: (p: { dataIndex: number; value: number }) => {
          const ft = f[f.length - 1 - p.dataIndex]
          const color = ft.dir === 'green' ? getCSSVar('--green-bright') : getCSSVar('--risk-4')
          const tag = ft.dir === 'green' ? '韧性因子 · 降风险' : '致灾因子 · 推风险'
          const pct = (p.value * 100).toFixed(1)
          return `<b>${ft.name}</b> <span style="color:${getCSSVar('--text-3')};font-family:JetBrains Mono;font-size:10px;">${ft.en}</span><br/>
            <span style="font-family:JetBrains Mono;color:${color};font-size:16px;font-weight:600;">${pct}%</span>
            <span style="font-family:JetBrains Mono;color:${getCSSVar('--text-3')};font-size:11px;margin-left:4px;">mean|SHAP|</span><br/>
            <span style="font-size:11px;color:${getCSSVar('--text-2')};">${tag}</span><br/>
            <span style="font-size:10px;color:${getCSSVar('--text-3')};font-family:JetBrains Mono;">原始 abs 贡献 ${ft.rawAbs.toExponential(2)}</span>`
        },
      },
      xAxis: {
        type: 'value',
        max: xMax,
        splitLine: { lineStyle: { color: getCSSVar('--border'), type: 'dashed' } },
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: {
          color: getCSSVar('--text-3'),
          fontFamily: 'JetBrains Mono',
          fontSize: 10,
          formatter: (v: number) => (v * 100).toFixed(0) + '%',
        },
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
            formatter: (p: { value: number }) => (p.value * 100).toFixed(1) + '%',
          },
          animationDuration: motionDuration(800),
        },
      ],
    },
    true,
  )
}

function renderContribBars() {
  if (!waterfallChart) return
  const bars = contribBars.value
  if (bars.length === 0) {
    waterfallChart.clear()
    return
  }
  // y 轴对称自适应:最大 abs 贡献 × 1.18 留 label padding。
  const maxAbs = bars.reduce((m, b) => Math.max(m, Math.abs(b.value)), 0) || 0.001
  const axisAbs = +(maxAbs * 1.18).toFixed(4)

  waterfallChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 16, right: 16, top: 16, bottom: 72 },
      tooltip: {
        trigger: 'item',
        backgroundColor: getCSSVar('--bg-elev'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 12 },
        formatter: (p: { dataIndex: number }) => {
          const b = bars[p.dataIndex]
          const color = b.value >= 0 ? getCSSVar('--risk-4') : getCSSVar('--green-bright')
          const sign = b.value >= 0 ? '+' : '−'
          const tag = b.value >= 0 ? '致灾因子 · 推升风险' : '韧性因子 · 降低风险'
          return `<b>${b.name}</b> <span style="color:${getCSSVar('--text-3')};font-family:JetBrains Mono;font-size:10px;">${b.en}</span><br/>
            <span style="font-family:JetBrains Mono;color:${color};font-size:16px;font-weight:600;">${sign}${Math.abs(b.value).toFixed(4)}</span>
            <span style="font-family:JetBrains Mono;color:${getCSSVar('--text-3')};font-size:11px;margin-left:4px;">SHAP 贡献</span><br/>
            <span style="font-size:11px;color:${getCSSVar('--text-2')};">${tag} · 相对跨省均值</span>`
        },
      },
      xAxis: {
        type: 'category',
        data: bars.map((b) => b.name),
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text-2'), fontFamily: 'Noto Sans SC', fontSize: 10, interval: 0, rotate: 32 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        min: -axisAbs,
        max: axisAbs,
        splitLine: { lineStyle: { color: getCSSVar('--border'), type: 'dashed' } },
        axisLine: { show: false },
        axisLabel: { color: getCSSVar('--text-3'), fontFamily: 'JetBrains Mono', fontSize: 10, formatter: (v: number) => v.toFixed(3) },
      },
      series: [
        {
          type: 'bar',
          data: bars.map((b) => ({
            value: b.value,
            itemStyle: {
              color: b.value >= 0 ? getCSSVar('--risk-4') : getCSSVar('--green'),
              borderRadius: b.value >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
            },
          })),
          barWidth: 20,
          label: {
            show: true,
            position: (p: { value: number }) => (p.value >= 0 ? 'top' : 'bottom'),
            color: getCSSVar('--text-2'),
            fontFamily: 'JetBrains Mono',
            fontSize: 9,
            formatter: (p: { value: number }) => (p.value >= 0 ? '+' : '−') + Math.abs(p.value).toFixed(3),
          },
          animationDuration: motionDuration(700),
          animationDurationUpdate: motionDuration(400),
        },
      ],
    },
    true,
  )
}

function renderBeeswarm() {
  if (!beeswarmChart) return
  const { features: featNames, points } = generateBeeswarmPoints()
  if (featNames.length === 0) {
    beeswarmChart.clear()
    return
  }
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
            <span style="font-size:11px;color:${getCSSVar('--text-2')};">${p.value[0] >= 0 ? '推升' : '降低'}风险 · 示意分布</span>`
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
  renderContribBars()
  renderBeeswarm()
}

// 重要性图刷新触发条件:
//   - backendNormalized / backendContribs: 单省 SHAP 拉取完成
//   - subsetData: 子集聚合拉取完成
//   - currentSubsetKey: 模式切换(single ↔ subset)即使数据没变也要重绘
//     (例如 single 数据已存在, 从 'all' 切回 'single' 不触发上面任何 ref 变更)
watch([backendNormalized, backendContribs, subsetData, currentSubsetKey], () => {
  renderImportance()
}, { flush: 'post' })

// M02-B 带向贡献 + M02-C 蜂群:数据源是单省 SHAP(FEATURES_ALL,不随 subset 切换),
// 故只盯 backendNormalized / backendContribs。切换 TARGET 省份 → fetchShapData 刷新
// 这两个 ref → 两图同步重绘(修复"切省份归因不变")。
watch([backendNormalized, backendContribs], () => {
  renderContribBars()
  renderBeeswarm()
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
  // 默认 'single' 模式,bar chart 与 waterfall 共用单省 SHAP 数据源,
  // 只需触发一次 fetchShapData。subset 数据 lazy 拉取(切到 north/south/...
  // 时才请求 backend),省一次冷启动等待。
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
        对当前选定省份
        <b v-if="selectedProvince?.name">{{ selectedProvince.name }}</b>
        <b v-else>—</b>
        解析 XGBoost-SHAP 省内风险因子相对重要性,
        从全局重要性、单样本预测分解到蜂群分布三个视角呈现互补归因视角。
        <span
          v-if="storeLoading || isLoadingShap"
          class="shap-status loading"
          aria-hidden="true"
        >
          <span class="lead-spinner"></span>
        </span>
        <span v-else-if="shapDataSource === 'error'" class="shap-status err">· 暂无可用结果</span>
      </p>
      <p v-if="selectedProvince?.name" class="province-line">
        当前省份 <b>{{ selectedProvince.name }}</b>
        <span class="prov-meta">{{ selectedProvince.type }} · y={{ selectedProvince.y.toFixed(4) }}</span>
      </p>
    </header>

    <!-- M02-0 · 目标省份切换器(与 M03/M04 共享 Pinia store) -->
    <div class="target-bar card">
      <div class="target-head">
        <div>
          <div class="num">M02-0 · TARGET</div>
          <h3 id="shap-target-heading">选择省份</h3>
        </div>
        <span
          v-if="storeLoading"
          class="status loading"
          aria-label="正在加载"
          role="status"
          aria-live="polite"
        >
          <span class="status-spinner" aria-hidden="true"></span>
        </span>
      </div>
      <!-- a11y SC 1.3.1 + 4.1.2:select 显式 label 关联 -->
      <label class="sr-only" for="province-select-shap">SHAP 归因目标省份选择器</label>
      <select
        id="province-select-shap"
        v-model.number="selectedIdx"
        class="province-select"
        aria-labelledby="shap-target-heading"
        :disabled="storeLoading"
      >
        <option v-for="(p, i) in profiles" :key="p.name" :value="i">
          {{ p.name }} · {{ p.type }}
        </option>
      </select>
    </div>

    <!-- 主 grid 3 chart -->
    <div class="grid" role="region" aria-label="SHAP 归因图表区">
      <div class="card chart-card">
        <div class="card-head">
          <div>
            <div class="num">M02-A · GLOBAL IMPORTANCE</div>
            <h3>全局特征重要性 mean(|SHAP|)</h3>
            <div v-if="subsetSubtitle" class="subset-subtitle">{{ subsetSubtitle }}</div>
          </div>
          <div
            class="subset-toggle"
            role="tablist"
            aria-label="全局重要性子集切换"
          >
            <button
              v-for="s in SUBSETS"
              :key="s.key"
              type="button"
              role="tab"
              :aria-selected="currentSubsetKey === s.key"
              :class="{ active: currentSubsetKey === s.key }"
              :disabled="subsetLoading && currentSubsetKey !== s.key"
              @click="currentSubsetKey = s.key"
            >
              <template v-if="s.key === 'single' && selectedProvince?.name">
                {{ s.label }} · {{ selectedProvince.name }}
              </template>
              <template v-else>
                {{ s.label }}
              </template>
            </button>
          </div>
        </div>
        <!-- a11y SC 1.1.1:ECharts canvas 加 role/aria-label 文本替代 -->
        <div
          ref="importanceEl"
          class="chart-canvas"
          role="img"
          aria-label="全局特征重要性条形图,按平均 SHAP 绝对值排序展示驱动因子"
          tabindex="0"
        ></div>
        <!-- loading overlay:single 模式拉单省 SHAP / subset 模式聚合 backend -->
        <div
          v-if="(currentSubsetKey === 'single' ? isLoadingShap : subsetLoading) && features.length === 0"
          class="chart-overlay"
        >
          <div class="spinner" aria-hidden="true"></div>
          <div>{{ currentSubsetKey === 'single' ? '正在计算单省 SHAP' : '正在聚合子集 SHAP' }}</div>
        </div>
        <!-- error overlay:retry 按 mode 调对应 fetch -->
        <div
          v-else-if="currentSubsetKey === 'single'
            ? (shapDataSource === 'error' && features.length === 0)
            : (subsetError && !subsetData && features.length === 0)"
          class="chart-overlay err"
        >
          <div>暂无可用结果</div>
          <button
            type="button"
            class="retry-btn"
            @click="currentSubsetKey === 'single' ? fetchShapData() : fetchSubset(currentSubsetKey)"
          >
            重试
          </button>
        </div>
      </div>

      <div class="card chart-card">
        <div class="card-head">
          <div>
            <div class="num">M02-B · SIGNED CONTRIBUTION · 当前省份</div>
            <h3>省内因子带向贡献</h3>
          </div>
          <span class="hint">最强 {{ contribHeadline }}</span>
        </div>
        <div
          ref="waterfallEl"
          class="chart-canvas"
          role="img"
          :aria-label="`${selectedProvince?.name ?? ''} 省内各因子带符号 SHAP 贡献柱状图:红色向上为推升风险,绿色向下为降低风险,按贡献绝对值排序`"
          tabindex="0"
        ></div>
      </div>

      <div class="card chart-card full">
        <div class="card-head">
          <div>
            <div class="num">M02-C · BEESWARM · 当前省份 Top-5</div>
            <h3>Top 5 因子 SHAP 分布(示意)</h3>
          </div>
          <span class="hint">围绕本省真实带向贡献的示意分布&nbsp;·&nbsp;X = SHAP 方向</span>
        </div>
        <div
          ref="beeswarmEl"
          class="chart-canvas"
          role="img"
          :aria-label="`${selectedProvince?.name ?? ''} Top 5 因子 SHAP 示意分布散点图:每个因子点云围绕其真实带向贡献展开,横轴左侧减损、右侧增灾`"
          tabindex="0"
        ></div>
      </div>
    </div>

  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1480px; margin: 0 auto; }

.page-head { margin-bottom: 20px; }
.eyebrow { font-family: var(--font-mono); font-size: 10px; color: var(--green); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 8px; }
.page-head h2 { font-family: var(--font-serif); font-size: 26px; font-weight: 600; margin-bottom: 6px; }
.lead { font-size: 13px; color: var(--text-2); max-width: 920px; line-height: 1.7; }
.shap-status {
  font-family: var(--font-mono);
  font-size: 11px;
  margin-left: 6px;
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
}
.shap-status.err { color: var(--text-3); }
.lead-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid var(--bg-elev);
  border-top-color: var(--green-bright);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
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

/* target bar(省份切换器) */
.target-bar { margin-bottom: 16px; }
.target-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.target-head .num { font-family: var(--font-mono); font-size: 9px; color: var(--text-3); letter-spacing: 1px; margin-bottom: 2px; }
.target-head h3 { font-family: var(--font-serif); font-size: 14px; font-weight: 600; }

.province-select {
  width: 100%;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--text);
  padding: 10px 12px;
  font-size: 12px;
  font-family: var(--font-sans);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M0 0l5 6 5-6z' fill='%236B7A72'/></svg>");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 8px;
}
.province-select:disabled { opacity: 0.55; cursor: wait; }
/* a11y SC 2.4.11 Focus Appearance:替代 outline:none */
.province-select:focus { border-color: var(--green); }
.province-select:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
  border-color: var(--green-bright);
}

.status {
  display: inline-flex;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
}
.status.loading { padding: 2px 6px; background: rgba(230, 182, 85, 0.10); border-radius: 8px; }
.status-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(230, 182, 85, 0.25);
  border-top-color: var(--amber);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

/* main grid */
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 420px 420px;
  gap: 16px;
}
/* 平板竖屏:2×2 图表网格改单列纵向堆叠,保留各图高度 */
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
    grid-template-rows: repeat(4, 400px);
  }
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
.chart-overlay.err { color: var(--text-3); }
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

/* M02-A SUBSET 4-button toggle(card-head 内右上)─────────────────────── */
.subset-toggle {
  display: inline-flex;
  gap: 2px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  padding: 2px;
}
.subset-toggle button {
  padding: 4px 10px;
  border: none;
  border-radius: calc(var(--r-md) - 4px);
  background: transparent;
  color: var(--text-3);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.3px;
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.subset-toggle button:hover:not(.active):not(:disabled) {
  color: var(--text);
}
.subset-toggle button.active {
  background: var(--green-deep, rgba(160, 183, 133, 0.18));
  color: var(--green-bright);
  font-weight: 600;
}
.subset-toggle button:disabled {
  opacity: 0.45;
  cursor: wait;
}
.subset-toggle button:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.subset-subtitle {
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.2px;
}

</style>
