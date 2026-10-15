<script setup lang="ts">
/**
 * M07-A 县级风险地图(ECharts choropleth)。
 *
 * 只负责"渲染 + 交互",数据由父视图注入(props),选中事件 emit 出去 —— 保持组件单纯。
 * 口径:着色用 `risk_level`(由 clim_anomaly 的年内分位切成 5 档),色阶沿用 M01 的 --risk-1..5;
 *       tooltip 同时给"气候异常 Δ"与"该县当年粮食产量",避免只靠颜色传达信息。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { CountyRow } from '@/api/county'
import { getCSSVar } from '@/data/mockProvinces'
import { motionDuration } from '@/data/a11y'

const props = defineProps<{
  rows: CountyRow[]
  selectedCode: number | null
  loading: boolean
  error: string | null
}>()

const emit = defineEmits<{ (e: 'select', code: number): void }>()

const MAP_NAME = 'counties-10-provinces'
const MAP_URL = '/maps/counties_10provinces.json'

const mapEl = ref<HTMLDivElement | null>(null)
const mapReady = ref(false)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const RISK_LABELS = ['低', '较低', '中等', '较高', '高']

function render() {
  if (!chart) return
  const data = props.rows
    .filter((r) => r.on_map)
    .map((r) => ({
      name: r.map_key,
      value: r.risk_level,
      code: r.county_code,
      county: r.county,
      province: r.province,
      anomaly: r.clim_anomaly,
      output: r.grain_output_t,
      unitType: r.unit_type,
    }))

  chart.setOption(
    {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: getCSSVar('--bg-card'),
        borderColor: getCSSVar('--border-strong'),
        borderWidth: 1,
        textStyle: { color: getCSSVar('--text'), fontFamily: 'Noto Sans SC, sans-serif', fontSize: 12 },
        extraCssText: 'border-radius: 4px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); padding: 10px 14px;',
        formatter: (p: { name: string; data?: unknown }) => {
          const d = p.data as
            | { county: string; province: string; value: number; anomaly: number; output: number | null; unitType: string }
            | undefined
          if (!d) {
            return `<div style="font-family:'Noto Serif SC';font-size:13px;">${p.name}</div>
              <div style="color:${getCSSVar('--text-3')};font-size:11px;">该县不在县级面板内</div>`
          }
          const tag = d.unitType === 'urban'
            ? `<span style="color:${getCSSVar('--amber-bright')};font-size:11px;">非主产单元</span>`
            : ''
          return `
            <div style="font-family:'Noto Serif SC';font-size:14px;font-weight:600;margin-bottom:4px;">
              ${d.county}${tag ? ' · ' + tag : ''}
            </div>
            <div style="color:${getCSSVar('--text-2')};font-size:11px;margin-bottom:6px;">${d.province}</div>
            <div style="font-family:'JetBrains Mono';color:${getCSSVar('--risk-4')};font-size:16px;font-weight:600;">
              风险等级 ${d.value} · ${RISK_LABELS[d.value - 1] ?? ''}
            </div>
            <div style="color:${getCSSVar('--text-2')};font-size:11px;margin-top:4px;">
              气候异常 Δ ${d.anomaly >= 0 ? '+' : ''}${d.anomaly.toFixed(3)}
            </div>
            <div style="color:${getCSSVar('--text-3')};font-size:11px;">
              当年粮食产量 ${d.output == null ? '无数据' : Math.round(d.output).toLocaleString('zh-CN') + ' 吨'}
            </div>
          `
        },
      },
      visualMap: {
        show: false,
        type: 'piecewise',
        min: 1,
        max: 5,
        inRange: {
          color: [
            getCSSVar('--risk-1'),
            getCSSVar('--risk-2'),
            getCSSVar('--risk-3'),
            getCSSVar('--risk-4'),
            getCSSVar('--risk-5'),
          ],
        },
      },
      series: [
        {
          type: 'map',
          map: MAP_NAME,
          roam: true,
          scaleLimit: { min: 1, max: 12 },
          zoom: 1.2,
          selectedMode: false,
          // 1,248 个县级面里约 79 个无面板数据 —— 用底色 + 淡边区分"无数据"与"低风险"
          itemStyle: {
            areaColor: getCSSVar('--bg-elev'),
            borderColor: getCSSVar('--bg'),
            borderWidth: 0.4,
          },
          emphasis: {
            label: { show: false },
            itemStyle: {
              areaColor: getCSSVar('--green-bright'),
              borderColor: getCSSVar('--text'),
              borderWidth: 1.2,
            },
          },
          label: { show: false },
          select: {
            label: { show: false },
            itemStyle: { areaColor: getCSSVar('--green-bright'), borderColor: getCSSVar('--text'), borderWidth: 1.4 },
          },
          data,
        },
      ],
      animationDuration: motionDuration(500),
      animationDurationUpdate: motionDuration(300),
    },
    true,
  )

  // 选中态单独下发:选中县高亮,不依赖 ECharts 的 select 内部状态
  if (props.selectedCode != null) {
    chart.dispatchAction({ type: 'highlight', seriesIndex: 0, name: selectedName() })
  }
}

function selectedName(): string {
  return props.rows.find((r) => r.county_code === props.selectedCode)?.map_key ?? ''
}

async function init() {
  if (!mapEl.value) return
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 10000)
    const resp = await fetch(MAP_URL, { signal: ctrl.signal })
    clearTimeout(timer)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const geojson = await resp.json()
    echarts.registerMap(MAP_NAME, geojson as Parameters<typeof echarts.registerMap>[1])
    chart = echarts.init(mapEl.value, undefined, { renderer: 'canvas' })
    chart.on('click', (params) => {
      const code = (params.data as { code?: number } | undefined)?.code
      if (typeof code === 'number') emit('select', code)
    })
    mapReady.value = true
    render()
  } catch (e) {
    mapReady.value = false
    console.error('[county-map] 边界加载失败', e)
  }
}

onMounted(() => {
  void init()
  if (mapEl.value && 'ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(mapEl.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

watch(() => props.rows, render, { deep: false })
watch(() => props.selectedCode, render)

defineExpose({ mapReady })
</script>

<template>
  <div class="map-wrap">
    <!-- a11y SC 1.1.1 + SC 1.4.1:canvas 无文本替代,role="img" + aria-label,
         文字替代见页面里的「高风险县清单」(aria-describedby 指向它)。 -->
    <div
      ref="mapEl"
      class="map-canvas"
      role="img"
      :aria-label="`县级粮食生产气候风险地图，${rows.length} 个县，赭石色越深表示当年气候条件相对本县常年越不利`"
      aria-describedby="county-top-list-desc"
      tabindex="0"
    ></div>
    <div v-if="loading" class="map-overlay" role="status" aria-live="polite">
      <span class="spinner" aria-hidden="true"></span>
      <span>正在加载县级面板…</span>
    </div>
    <div v-else-if="error" class="map-overlay error" role="alert">
      <span aria-hidden="true">⚠</span>
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<style scoped>
.map-wrap {
  position: relative;
  min-height: 520px;
  height: 100%;
}
.map-canvas {
  width: 100%;
  height: 100%;
  min-height: 520px;
}
.map-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-3);
  background: rgba(22, 37, 32, 0.72);
  color: var(--text-2);
  font-size: 13px;
}
.map-overlay.error { color: var(--amber-bright); }
.spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--border-strong);
  border-top-color: var(--green-bright);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
