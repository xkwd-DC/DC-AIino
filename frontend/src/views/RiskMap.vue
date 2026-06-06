<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { storeToRefs } from 'pinia'
import { useProvinceStore } from '@/stores/useProvinceStore'
import { fetchProvinces, fetchProvinceHistory, type ProvinceRow } from '@/api/province'
import {
  RANGES,
  YEARS,
  YEAR_MAX,
  YEAR_MIN,
  getCSSVar,
  percentile,
  riskColorResolved,
  riskColorVar,
  type ProvinceSnapshot,
} from '@/data/mockProvinces'
// a11y: ECharts canvas 动画绕过 CSS prefers-reduced-motion,需 JS 探测后传 0。
import { motionDuration, prefersReducedMotion } from '@/data/a11y'

// HIGH#3: 走自托管 /maps/china.json (PR #34 入仓的 61KB GeoJSON)，
// 消除 CDN 单点故障 + 8s timeout 风险。SHA-256 记录见 frontend/public/maps/README.md。
const CHINA_MAP_URL = '/maps/china.json'

const mapEl = ref<HTMLDivElement | null>(null)
const miniEl = ref<HTMLDivElement | null>(null)

const currentYear = ref(YEAR_MAX)
const hoveredProvince = ref<string | null>(null)
const mapLoading = ref(true)
const mapError = ref<string | null>(null)

let mapChart: echarts.ECharts | null = null
let miniChart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

// ── 真后端 store:31 省 latest 数据(/api/provinces) ─────────────────────────
const provinceStore = useProvinceStore()
const { provinces, isLoading: storeLoading, error: storeError, source: storeSource } = storeToRefs(provinceStore)

// ── 年度数据缓存:slider 切年时按需 fetch /api/provinces?year=Y ──────────────
// 设计:
//   - 初始(mount)由 store.loadProvinces() 拉默认年 → 缓存到 yearCache[YEAR_MAX]
//   - slider 拖动后,若该年未在缓存,异步 fetch;
//     fetch 失败(grain.db 未就绪,后端返 503)→ 复用 latest 年的数据 + 标 fallback
//   - 不再生成 13 年合成 mock(去掉 ALL_DATA 依赖)
const yearCache = ref<Record<number, ProvinceSnapshot[]>>({})
const yearLoading = ref(false)
const yearFallback = ref(false)        // 当年 fetch 失败,正在用 latest 数据回退
const fallbackNote = ref<string | null>(null)

/** 把 API 行规整成 view 用的 ProvinceSnapshot 结构。
 *  grain.db 行字段是 flood_r;baseline json 用 flood。统一映射到 flood。 */
function rowToSnapshot(row: ProvinceRow): ProvinceSnapshot {
  return {
    name: row.name ?? row.province ?? '未知',
    y: row.y ?? 0,
    irr: row.irr ?? 0,
    flood: row.flood ?? row.flood_r ?? 0,
    sun: row.sun ?? 0,
    spei: row.spei ?? 0,
    temp: row.temp ?? 0,
    type: row.type ?? '主产区主导型',
  }
}

const currentData = computed<ProvinceSnapshot[]>(() => yearCache.value[currentYear.value] ?? [])

const avgY = computed(() => {
  const arr = currentData.value
  if (arr.length === 0) return 0
  return arr.reduce((s, d) => s + d.y, 0) / arr.length
})

const deltaPct = computed<number | null>(() => {
  if (currentYear.value <= YEAR_MIN) return null
  const prev = yearCache.value[currentYear.value - 1]
  if (!prev || prev.length === 0) return null
  const prevAvg = prev.reduce((s, d) => s + d.y, 0) / prev.length
  if (prevAvg === 0) return null
  return ((avgY.value - prevAvg) / prevAvg) * 100
})

const top10 = computed(() => {
  return [...currentData.value].sort((a, b) => b.y - a.y).slice(0, 10)
})

const detail = computed<ProvinceSnapshot | null>(() => {
  if (!hoveredProvince.value) return null
  return currentData.value.find((d) => d.name === hoveredProvince.value) ?? null
})

// ── 单省 13 年时序(/api/provinces/<name>/history) ──────────────────────────
const detailHistorySeries = ref<Array<number | null>>([])
const detailHistoryLoading = ref(false)
const detailHistoryError = ref<string | null>(null)

const sliderFillPct = computed(() => {
  return ((currentYear.value - YEAR_MIN) / (YEAR_MAX - YEAR_MIN)) * 100
})

function renderMap() {
  if (!mapChart) return
  const data = currentData.value
  const mapData = data.map((d) => ({ name: d.name, value: d.y, type: d.type }))

  mapChart.setOption(
    {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: getCSSVar('--bg-card'),
        borderColor: getCSSVar('--border-strong'),
        borderWidth: 1,
        textStyle: { color: getCSSVar('--text'), fontFamily: 'Noto Sans SC, sans-serif', fontSize: 12 },
        extraCssText: 'border-radius: 4px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); padding: 10px 14px;',
        formatter: (p: { name: string; value: number | undefined }) => {
          if (p.value == null || isNaN(p.value)) {
            return `<b>${p.name}</b><br/><span style="color:${getCSSVar('--text-3')}">无数据</span>`
          }
          const item = data.find((d) => d.name === p.name)
          return `
            <div style="font-family:'Noto Serif SC';font-size:14px;font-weight:600;margin-bottom:4px;">${p.name}</div>
            <div style="font-family:'JetBrains Mono';color:${getCSSVar('--green-bright')};font-size:18px;font-weight:600;">${p.value.toFixed(4)}</div>
            <div style="color:${getCSSVar('--text-2')};font-size:11px;margin-top:2px;">${item?.type ?? ''}</div>
          `
        },
      },
      visualMap: {
        show: false,
        min: 0.011,
        max: 0.043,
        inRange: {
          color: [getCSSVar('--risk-1'), getCSSVar('--risk-2'), getCSSVar('--risk-3'), getCSSVar('--risk-4'), getCSSVar('--risk-5')],
        },
      },
      series: [
        {
          type: 'map',
          map: 'china',
          roam: true,
          scaleLimit: { min: 0.8, max: 4 },
          zoom: 1.15,
          itemStyle: {
            areaColor: getCSSVar('--bg-elev'),
            borderColor: getCSSVar('--border-strong'),
            borderWidth: 0.6,
          },
          emphasis: {
            label: { show: true, color: '#0E1A14', fontWeight: 'bold', fontSize: 12, textBorderColor: 'transparent' },
            itemStyle: {
              areaColor: getCSSVar('--green-bright'),
              borderColor: getCSSVar('--text'),
              borderWidth: 1.5,
            },
          },
          label: {
            show: true,
            color: '#FFFFFF',
            fontSize: 9,
            fontFamily: 'Noto Sans SC',
            textBorderColor: 'rgba(0, 0, 0, 0.6)',
            textBorderWidth: 2,
          },
          data: mapData,
        },
      ],
      // a11y SC 2.3.3:reduced-motion 时 ECharts 自身动画归零
      animationDuration: motionDuration(600),
      animationDurationUpdate: motionDuration(400),
    },
    true,
  )
}

function renderMiniChart() {
  if (!miniEl.value || !detail.value) return
  if (!miniChart) {
    miniChart = echarts.init(miniEl.value, undefined, { renderer: 'canvas' })
  }
  const series = detailHistorySeries.value
  // 若 series 为空(historical API 不可用),直接清空 mini chart
  if (series.length === 0) {
    miniChart.clear()
    return
  }
  const currentIdx = currentYear.value - YEAR_MIN

  miniChart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 0, right: 0, top: 6, bottom: 6 },
      xAxis: { type: 'category', show: false, data: YEARS },
      yAxis: { type: 'value', show: false, scale: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: getCSSVar('--bg-elev'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 11 },
        formatter: (params: Array<{ axisValue: string; value: number }>) => {
          const p = params[0]
          const v = p.value
          return `${p.axisValue} · <b style="color:${getCSSVar('--green-bright')}">${v?.toFixed?.(4) ?? '—'}</b>`
        },
      },
      series: [
        {
          type: 'line',
          data: series,
          smooth: true,
          symbol: 'none',
          lineStyle: { color: getCSSVar('--green'), width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(160, 183, 133, 0.4)' },
                { offset: 1, color: 'rgba(160, 183, 133, 0)' },
              ],
            },
          },
          markPoint: {
            symbol: 'circle',
            symbolSize: 8,
            data: series[currentIdx] != null ? [{ coord: [currentIdx, series[currentIdx]] }] : [],
            itemStyle: { color: getCSSVar('--green-bright'), borderColor: getCSSVar('--bg'), borderWidth: 2 },
            label: { show: false },
          },
        },
      ],
      animation: !prefersReducedMotion(),
      animationDuration: motionDuration(400),
    },
    true,
  )
}

async function loadMap() {
  if (!mapEl.value) return
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 8000)
    const resp = await fetch(CHINA_MAP_URL, { signal: ctrl.signal })
    clearTimeout(timer)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const geoJson = await resp.json()
    echarts.registerMap('china', geoJson as Parameters<typeof echarts.registerMap>[1])
    mapChart = echarts.init(mapEl.value, undefined, { renderer: 'canvas' })
    renderMap()
    mapLoading.value = false

    let hoverTimer: ReturnType<typeof setTimeout> | null = null
    mapChart.on('mouseover', { seriesType: 'map' }, (params: { name: string }) => {
      if (hoverTimer) clearTimeout(hoverTimer)
      hoverTimer = setTimeout(() => {
        hoveredProvince.value = params.name
      }, 150)
    })

    resizeObserver = new ResizeObserver(() => mapChart?.resize())
    resizeObserver.observe(mapEl.value)
  } catch (e) {
    // HIGH#4: 仅 dev 输出到 console,production 仅走 UI mapError 状态展示
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.error('[risk-map] geoJson load failed', e)
    }
    mapError.value = (e as Error).message || 'network error'
    mapLoading.value = false
  }
}

/** 初始化:用 store.loadProvinces() 拉 latest year(默认走 /api/provinces 无参) */
async function initProvinces() {
  await provinceStore.loadProvinces()
  // store 已 normalize 为 ProvinceBase,view 用同样 schema 的 ProvinceSnapshot
  // (type 等可选字段已对齐),直接复用。
  yearCache.value[YEAR_MAX] = provinces.value.map((p) => ({ ...p }))
}

/** 切年时按需 fetch。grain.db 未加载会 503 → 标 fallback,view 沿用 latest 数据。 */
async function loadYear(year: number) {
  if (yearCache.value[year]) return // 已缓存
  if (year === YEAR_MAX) return // 已由 init 填充
  yearLoading.value = true
  fallbackNote.value = null
  try {
    const rows = await fetchProvinces(year)
    yearCache.value[year] = rows.map(rowToSnapshot)
    yearFallback.value = false
  } catch (e: unknown) {
    // 503 / 网络错误 → 复用 latest 年数据,提示用户
    yearCache.value[year] = yearCache.value[YEAR_MAX] ?? []
    yearFallback.value = true
    const msg = e instanceof Error ? e.message : 'network error'
    fallbackNote.value = `${year} 年时序数据未就绪(${msg});展示 ${YEAR_MAX} 年基线快照`
  } finally {
    yearLoading.value = false
  }
}

/** 拉单省 13 年时序(history)。grain.db 未加载会 503 → 隐藏 mini chart。 */
async function loadHistory(name: string) {
  detailHistoryLoading.value = true
  detailHistoryError.value = null
  detailHistorySeries.value = []
  try {
    const hist = await fetchProvinceHistory(name)
    // 把 series 按 YEARS 顺序补齐;后端可能返回不连续年份。
    const map = new Map(hist.series.map((s) => [s.year, s.y_butter ?? s.yield_kg_per_ha ?? null]))
    detailHistorySeries.value = YEARS.map((y) => {
      const v = map.get(y)
      return typeof v === 'number' ? v : null
    })
  } catch (e: unknown) {
    detailHistoryError.value = e instanceof Error ? e.message : 'network error'
    // 失败保留空 series,renderMiniChart 会清空
    detailHistorySeries.value = []
  } finally {
    detailHistoryLoading.value = false
  }
}

function onRowClick(name: string) {
  hoveredProvince.value = name
  if (mapChart) {
    mapChart.dispatchAction({ type: 'highlight', name })
    setTimeout(() => mapChart?.dispatchAction({ type: 'downplay', name }), 1500)
  }
}

// a11y SC 2.1.1 Keyboard:Top10 行 / tick 用 Enter/Space 触发等价 click
function onRowKey(e: KeyboardEvent, name: string) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    onRowClick(name)
  }
}
function onTickKey(e: KeyboardEvent, y: number) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    currentYear.value = y
  }
}

async function retryInit() {
  mapLoading.value = true
  mapError.value = null
  await initProvinces()
  if (!mapChart) await loadMap()
  else renderMap()
  mapLoading.value = false
}

watch(currentYear, async (y) => {
  await loadYear(y)
  renderMap()
  if (detail.value) renderMiniChart()
})

watch(detail, async (d) => {
  if (d) {
    await loadHistory(d.name)
    // 等 detail 卡 DOM 渲染后再 init mini chart
    requestAnimationFrame(() => renderMiniChart())
  } else if (miniChart) {
    miniChart.dispose()
    miniChart = null
  }
})

onMounted(async () => {
  // 并行:先并发拉 geoJson + 31 省数据,然后渲染。
  await Promise.all([initProvinces(), loadMap()])
  // initProvinces 完成后再 render(map 已 init 在 loadMap 里)
  renderMap()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  miniChart?.dispose()
  mapChart?.dispose()
})

function fmtPct(p: number, digits = 1): string {
  return p.toFixed(digits)
}

// 抑制未用警告(percentile/riskColorResolved 模板内被用)
void percentile
void riskColorResolved
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M01 · SPATIO-TEMPORAL RISK MAP</div>
      <h2>风险时空地图</h2>
      <p class="lead">
        31 省 2011–2023 年粮食生产风险时空分布,直观呈现高风险省份与年际演化。
      </p>
    </header>

    <!-- 初始数据加载失败时的全局 banner(retry);仅在确实失败时显示。 -->
    <div
      v-if="storeError && storeSource === 'mock'"
      class="page-banner"
      role="alert"
      aria-live="assertive"
    >
      <span class="banner-icon" aria-hidden="true">⚠</span>
      <div class="banner-text">
        <b>数据正在同步,请稍后重试。</b>
        <button type="button" class="banner-retry" @click="retryInit">重新加载</button>
      </div>
    </div>

    <div class="grid">
      <!-- 左:地图 + 时间轴 -->
      <section class="map-panel">
        <div class="map-toolbar">
          <span class="num">M01-A</span>
          <h3>中国粮食生产风险分布</h3>
          <span v-if="yearLoading" class="map-status loading" aria-hidden="true">
            <span class="map-spinner"></span>
          </span>
          <span
            v-else-if="yearFallback"
            class="map-status fallback"
            :title="fallbackNote ?? ''"
          >
            展示最近年快照
          </span>
        </div>
        <div class="map-canvas-wrap">
          <!-- a11y SC 1.1.1 Non-text Content + SC 4.1.2:
               ECharts canvas 无文本替代,role="img" + aria-label + aria-describedby 指向 Top10 表 -->
          <div
            ref="mapEl"
            class="map-canvas"
            role="img"
            aria-label="中国 31 省粮食生产风险分布地图,使用颜色深浅表示风险高低,赭石色越深风险越高"
            aria-describedby="map-top10-desc"
            tabindex="0"
          ></div>
          <div
            v-if="mapLoading || storeLoading"
            class="map-state"
            role="status"
            aria-live="polite"
            aria-label="正在加载中国地图与省份数据"
          >
            <div class="spinner" aria-hidden="true"></div>
            <div>正在加载中国地图与省份数据…</div>
          </div>
          <div
            v-else-if="mapError"
            class="map-state error"
            role="alert"
            aria-live="assertive"
          >
            <div>⚠ 地图数据加载失败</div>
            <div class="small">{{ mapError }}</div>
            <button class="retry-btn" type="button" @click="retryInit">重试</button>
          </div>
        </div>

        <div class="timeline">
          <div class="timeline-head">
            <div>
              <div class="timeline-label">YEAR · 时间维度</div>
              <div class="timeline-year">{{ currentYear }}</div>
            </div>
            <span class="year-step">{{ YEAR_MIN }} — {{ YEAR_MAX }} · 13 年</span>
          </div>
          <div class="slider-track-wrap">
            <div class="slider-track" aria-hidden="true">
              <div class="slider-fill" :style="{ width: sliderFillPct + '%' }"></div>
            </div>
            <!-- a11y SC 1.3.1 + SC 4.1.2:range input 加 aria-label / valuemin/max/now / valuetext -->
            <input
              v-model.number="currentYear"
              type="range"
              :min="YEAR_MIN"
              :max="YEAR_MAX"
              step="1"
              class="native-range"
              :aria-label="`时间年份,${YEAR_MIN} 至 ${YEAR_MAX} 年`"
              :aria-valuemin="YEAR_MIN"
              :aria-valuemax="YEAR_MAX"
              :aria-valuenow="currentYear"
              :aria-valuetext="`${currentYear} 年`"
            />
            <!-- a11y SC 2.1.1:tick 加 role/tabindex/keyboard handler -->
            <div class="slider-ticks" role="group" aria-label="年份快捷跳转">
              <div
                v-for="y in YEARS"
                :key="y"
                class="tick"
                :class="{ active: y === currentYear }"
                role="button"
                tabindex="0"
                :aria-label="`跳转到 ${y} 年`"
                :aria-pressed="y === currentYear"
                @click="currentYear = y"
                @keydown="onTickKey($event, y)"
              >
                {{ String(y).slice(-2) }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 右:图例 + Top10 + 明细 -->
      <aside class="side-panel">
        <div class="card">
          <div class="card-head">
            <h3>风险图例</h3>
            <span class="meta">Y · DETRENDED VOLATILITY</span>
          </div>
          <div class="legend-body">
            <!-- a11y SC 1.1.1:图例色阶加 role/aria-label -->
            <div
              class="legend-bar"
              role="img"
              aria-label="风险色阶,从浅到深表示风险由低到高,共 5 级"
            >
              <div :style="{ background: 'var(--risk-1)' }" aria-hidden="true"></div>
              <div :style="{ background: 'var(--risk-2)' }" aria-hidden="true"></div>
              <div :style="{ background: 'var(--risk-3)' }" aria-hidden="true"></div>
              <div :style="{ background: 'var(--risk-4)' }" aria-hidden="true"></div>
              <div :style="{ background: 'var(--risk-5)' }" aria-hidden="true"></div>
            </div>
            <div class="legend-labels">
              <span>低 0.011</span>
              <span>0.043 高</span>
            </div>
            <div class="legend-meta">
              <span>当前年份全国均值</span>
              <span class="v">{{ avgY.toFixed(4) }}</span>
            </div>
            <div class="legend-meta">
              <span>较前年</span>
              <span
                v-if="deltaPct !== null"
                class="v"
                :style="{ color: deltaPct >= 0 ? 'var(--red, #B86F4D)' : 'var(--green-bright)' }"
              >
                {{ deltaPct >= 0 ? '▲ +' : '▼ ' }}{{ fmtPct(deltaPct) }}%
              </span>
              <span v-else class="v muted">— 起始年或无对照</span>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3 id="top10-heading">Top 10 高风险省份</h3>
            <span class="meta">YEAR {{ currentYear }}</span>
          </div>
          <!-- a11y(SC 1.3.1):列表语义化 + 供地图 aria-describedby 引用 -->
          <p id="map-top10-desc" class="sr-only">
            该地图配有右侧 Top 10 高风险省份列表,可使用 Tab 键聚焦各省并查看明细
          </p>
          <ul
            class="top10-body"
            role="list"
            aria-labelledby="top10-heading"
          >
            <!-- a11y SC 2.1.1 + SC 4.1.2:rank-row 转 button 语义,加 Enter/Space 键盘支持 -->
            <li
              v-for="(d, i) in top10"
              :key="d.name"
              class="rank-row"
              :class="{ active: d.name === hoveredProvince }"
              role="button"
              tabindex="0"
              :aria-label="`第 ${i + 1} 名 ${d.name},风险值 ${d.y.toFixed(4)},点击查看明细`"
              :aria-pressed="d.name === hoveredProvince"
              @click="onRowClick(d.name)"
              @keydown="onRowKey($event, d.name)"
            >
              <span class="rank-num" aria-hidden="true">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="rank-name">{{ d.name }}</span>
              <div class="rank-bar" aria-hidden="true">
                <div
                  class="rank-bar-fill"
                  :style="{
                    width: ((d.y - 0.011) / (0.043 - 0.011)) * 100 + '%',
                    background: riskColorVar(d.y),
                  }"
                ></div>
              </div>
              <span class="rank-val" :style="{ color: riskColorVar(d.y) }">{{ d.y.toFixed(4) }}</span>
            </li>
            <li v-if="top10.length === 0" class="rank-empty">
              <span v-if="storeLoading">正在加载省份数据…</span>
              <span v-else>暂无数据</span>
            </li>
          </ul>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>省份明细</h3>
            <span class="meta">{{ detail ? `${currentYear} · ${detail.type}` : 'HOVER / 点击 查看' }}</span>
          </div>
          <!-- a11y SC 4.1.3 Status Messages:省份明细变化通过 aria-live 朗读 -->
          <div class="detail-body" role="region" aria-live="polite" aria-atomic="true" aria-label="选中省份明细">
            <template v-if="detail">
              <div class="detail-province">
                <span>{{ detail.name }}</span>
                <span class="detail-y" :style="{ color: riskColorVar(detail.y) }">{{ detail.y.toFixed(4) }}</span>
              </div>
              <div class="detail-type">{{ detail.type }}</div>

              <div class="detail-stats">
                <div class="stat-row">
                  <span class="stat-label">风险指数 Y</span>
                  <div class="stat-progress">
                    <div class="stat-progress-fill" :style="{ width: percentile(detail.y, RANGES.y) + '%', background: 'var(--green)' }"></div>
                  </div>
                  <span class="stat-value">{{ detail.y.toFixed(4) }}</span>
                </div>
                <div class="stat-row">
                  <span class="stat-label">灌溉率 (%)</span>
                  <div class="stat-progress">
                    <div class="stat-progress-fill" :style="{ width: percentile(detail.irr, RANGES.irr) + '%', background: 'var(--blue)' }"></div>
                  </div>
                  <span class="stat-value">{{ detail.irr.toFixed(1) }}</span>
                </div>
                <div class="stat-row">
                  <span class="stat-label">洪涝占比 (%)</span>
                  <div class="stat-progress">
                    <div class="stat-progress-fill" :style="{ width: percentile(detail.flood, RANGES.flood) + '%', background: 'var(--blue)' }"></div>
                  </div>
                  <span class="stat-value">{{ detail.flood.toFixed(1) }}</span>
                </div>
                <div class="stat-row">
                  <span class="stat-label">日照时数 (h)</span>
                  <div class="stat-progress">
                    <div class="stat-progress-fill" :style="{ width: percentile(detail.sun, RANGES.sun) + '%', background: 'var(--amber)' }"></div>
                  </div>
                  <span class="stat-value">{{ Math.round(detail.sun) }}</span>
                </div>
                <div class="stat-row">
                  <span class="stat-label">SPEI 干旱指数</span>
                  <div class="stat-progress">
                    <div class="stat-progress-fill" :style="{ width: percentile(detail.spei, RANGES.spei) + '%', background: 'var(--purple)' }"></div>
                  </div>
                  <span class="stat-value">{{ detail.spei.toFixed(2) }}</span>
                </div>
              </div>

              <div class="detail-trend">
                <div class="trend-label">
                  <span>13 年风险趋势</span>
                  <span v-if="detailHistoryLoading" class="trend-status" aria-hidden="true">
                    <span class="trend-spinner"></span>
                  </span>
                  <span v-else-if="detailHistoryError" class="trend-status err">
                    暂无时序
                  </span>
                  <span v-else>{{ YEAR_MIN }} — {{ YEAR_MAX }}</span>
                </div>
                <!-- a11y SC 1.1.1:13 年趋势 mini chart 文本替代 -->
                <div
                  v-show="!detailHistoryError"
                  ref="miniEl"
                  class="mini-chart"
                  role="img"
                  :aria-label="`${detail?.name ?? ''} 省 ${YEAR_MIN} 至 ${YEAR_MAX} 年风险趋势小图`"
                ></div>
                <div v-if="detailHistoryError" class="mini-fallback">
                  趋势数据加载中
                </div>
              </div>
            </template>
            <template v-else>
              <div class="detail-empty">
                <span class="icon">◐</span>
                悬停或点击地图省份/Top10 查看明细
              </div>
            </template>
          </div>
        </div>
      </aside>
    </div>

  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1480px; margin: 0 auto; }

.page-head { margin-bottom: 24px; }
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
.lead { font-size: 13px; color: var(--text-2); max-width: 820px; line-height: 1.7; }

.page-banner {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 14px;
  margin-bottom: 16px;
  background: rgba(184, 111, 77, 0.08);
  border: 1px solid rgba(184, 111, 77, 0.35);
  border-radius: var(--r-md);
  font-size: 12px;
  color: var(--text-2);
}
.banner-icon { color: var(--risk-4); font-size: 16px; }
.banner-text { line-height: 1.6; }
.banner-retry {
  margin-left: 6px;
  padding: 3px 10px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  color: var(--green-bright);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
}
.banner-retry:hover { border-color: var(--green); }

.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(340px, 1fr);
  gap: 20px;
}
/* 平板竖屏:右侧图例/Top10 面板 340px 硬下限会挤压地图,改上下堆叠 */
@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
}

.map-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.map-toolbar {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.map-toolbar .num {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--green);
  letter-spacing: 1px;
}
.map-toolbar h3 {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 600;
}
.map-status {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.3px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.map-status.loading { color: var(--amber); }
.map-status.fallback { color: var(--text-3); }
.map-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid var(--bg-elev);
  border-top-color: var(--amber);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

.map-canvas-wrap {
  position: relative;
  height: 520px;
  border-radius: var(--r-md);
  background: var(--bg);
  overflow: hidden;
}
.map-canvas { position: absolute; inset: 0; }
.map-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: 12px;
}
.map-state .small { font-size: 10px; opacity: 0.7; }
.map-state.error { color: var(--red-bright, #C58866); }
.retry-btn {
  margin-top: 8px;
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
  width: 28px; height: 28px;
  border: 2px solid var(--bg-elev);
  border-top-color: var(--green);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.timeline {
  border-top: 1px solid var(--border);
  padding-top: 14px;
}
.timeline-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 12px;
}
.timeline-label {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1.2px;
  text-transform: uppercase;
}
.timeline-year {
  font-family: var(--font-mono);
  font-size: 32px;
  font-weight: 700;
  color: var(--green-bright);
  line-height: 1;
}
.year-step {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.5px;
}

.slider-track-wrap {
  position: relative;
  padding: 12px 0;
}
.slider-track {
  height: 4px;
  background: var(--bg-elev);
  border-radius: 2px;
  position: relative;
}
.slider-fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, var(--green-deep), var(--green-bright));
  border-radius: 2px;
  transition: width 0.2s var(--ease-out);
}
.native-range {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
  z-index: 2;
}
/* a11y SC 2.4.11 Focus Appearance:opacity:0 隐了原生 focus ring,
   focus 时给父 wrapper 加可见 ring,等价的视觉聚焦反馈 */
.slider-track-wrap:focus-within .slider-track {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
  border-radius: 4px;
}
.slider-ticks {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.3px;
}
.tick {
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 2px;
  transition: all var(--dur-fast);
}
.tick:hover { color: var(--text); }
.tick.active {
  color: var(--green-bright);
  background: rgba(160, 183, 133, 0.12);
}

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-head h3 {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 600;
}
.card-head .meta {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.legend-body { display: flex; flex-direction: column; gap: 10px; }
.legend-bar {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  height: 8px;
  border-radius: 2px;
  overflow: hidden;
}
.legend-labels {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.5px;
}
.legend-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-2);
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}
.legend-meta .v {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text);
}
.legend-meta .v.muted { color: var(--text-3); }

.top10-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
}
.top10-body::-webkit-scrollbar { width: 4px; }
.top10-body::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 2px; }

.rank-row {
  display: grid;
  grid-template-columns: 22px 56px 1fr 60px;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background var(--dur-fast);
}
.rank-row:hover { background: var(--bg-elev); }
.rank-row.active { background: rgba(160, 183, 133, 0.1); }
.rank-num {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
}
.rank-name {
  font-size: 12px;
  color: var(--text);
  font-weight: 500;
}
.rank-bar {
  height: 4px;
  background: var(--bg-elev);
  border-radius: 2px;
  overflow: hidden;
}
.rank-bar-fill { height: 100%; border-radius: 2px; transition: width 0.3s var(--ease-out); }
.rank-val {
  font-family: var(--font-mono);
  font-size: 11px;
  text-align: right;
  font-weight: 600;
}
.rank-empty {
  padding: 20px 8px;
  text-align: center;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
}

.detail-body { min-height: 180px; }
.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 36px 0;
  color: var(--text-3);
  font-size: 12px;
  text-align: center;
}
.detail-empty .icon { font-size: 28px; opacity: 0.4; }

.detail-province {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}
.detail-province > span:first-child {
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 600;
}
.detail-y {
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 600;
}
.detail-type {
  font-size: 11px;
  color: var(--text-3);
  margin-bottom: 14px;
}

.detail-stats { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.stat-row {
  display: grid;
  grid-template-columns: 100px 1fr 56px;
  align-items: center;
  gap: 10px;
  font-size: 11px;
}
.stat-label { color: var(--text-3); font-family: var(--font-mono); letter-spacing: 0.3px; }
.stat-progress {
  height: 4px;
  background: var(--bg-elev);
  border-radius: 2px;
  overflow: hidden;
}
.stat-progress-fill { height: 100%; border-radius: 2px; transition: width 0.3s var(--ease-out); }
.stat-value {
  font-family: var(--font-mono);
  font-weight: 600;
  text-align: right;
  color: var(--text);
}

.detail-trend {
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}
.trend-label {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.trend-status { color: var(--amber); display: inline-flex; align-items: center; gap: 4px; }
.trend-status.err { color: var(--text-3); }
.trend-spinner {
  display: inline-block;
  width: 8px;
  height: 8px;
  border: 1.5px solid var(--bg-elev);
  border-top-color: var(--amber);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
.mini-chart { height: 64px; }
.mini-fallback {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  background: var(--bg-elev);
  border-radius: var(--r-sm);
}

</style>
