<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import {
  ALL_DATA,
  PROVINCES_BASE,
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

const currentData = computed<ProvinceSnapshot[]>(() => ALL_DATA[currentYear.value] ?? [])

const avgY = computed(() => {
  const arr = currentData.value
  if (arr.length === 0) return 0
  return arr.reduce((s, d) => s + d.y, 0) / arr.length
})

const deltaPct = computed<number | null>(() => {
  if (currentYear.value <= YEAR_MIN) return null
  const prev = ALL_DATA[currentYear.value - 1]
  if (!prev) return null
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

const detailHistory = computed<Array<number | null>>(() => {
  if (!hoveredProvince.value) return []
  return YEARS.map((y) => {
    const d = ALL_DATA[y]?.find((x) => x.name === hoveredProvince.value)
    return d ? d.y : null
  })
})

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
    },
    true,
  )
}

function renderMiniChart() {
  if (!miniEl.value || !detail.value) return
  if (!miniChart) {
    miniChart = echarts.init(miniEl.value, undefined, { renderer: 'canvas' })
  }
  const series = detailHistory.value
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
          return `${p.axisValue} · <b style="color:${getCSSVar('--green-bright')}">${p.value.toFixed(4)}</b>`
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
            data: [{ coord: [currentIdx, series[currentIdx]] }],
            itemStyle: { color: getCSSVar('--green-bright'), borderColor: getCSSVar('--bg'), borderWidth: 2 },
            label: { show: false },
          },
        },
      ],
      animation: true,
      animationDuration: 400,
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
    // HIGH#4: 仅 dev 输出到 console，production 仅走 UI mapError 状态展示。
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.error('[risk-map] geoJson load failed', e)
    }
    mapError.value = (e as Error).message || 'network error'
    mapLoading.value = false
  }
}

function onRowClick(name: string) {
  hoveredProvince.value = name
  if (mapChart) {
    mapChart.dispatchAction({ type: 'highlight', name })
    setTimeout(() => mapChart?.dispatchAction({ type: 'downplay', name }), 1500)
  }
}

watch(currentYear, () => {
  renderMap()
  if (detail.value) renderMiniChart()
})

watch(detail, (d) => {
  if (d) {
    // 等 detail 卡 DOM 渲染后再 init mini chart
    requestAnimationFrame(() => renderMiniChart())
  } else if (miniChart) {
    miniChart.dispose()
    miniChart = null
  }
})

onMounted(() => {
  loadMap()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  miniChart?.dispose()
  mapChart?.dispose()
})

function fmtPct(p: number, digits = 1): string {
  return p.toFixed(digits)
}
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M01 · SPATIO-TEMPORAL RISK MAP</div>
      <h2>风险时空地图</h2>
      <p class="lead">
        31 省 2011–2023 年粮食生产风险时空分布。当前为前端 mock 数据演示，
        Phase 4（5/27-28）后将切换至 SQLite + <code>/api/provinces?year</code> 真实数据。
      </p>
    </header>

    <div class="grid">
      <!-- 左：地图 + 时间轴 -->
      <section class="map-panel">
        <div class="map-toolbar">
          <span class="num">M01-A</span>
          <h3>中国粮食生产风险分布</h3>
        </div>
        <div class="map-canvas-wrap">
          <div ref="mapEl" class="map-canvas"></div>
          <div v-if="mapLoading" class="map-state">
            <div class="spinner"></div>
            <div>正在加载中国地图…</div>
          </div>
          <div v-else-if="mapError" class="map-state error">
            <div>⚠ 地图数据加载失败</div>
            <div class="small">{{ mapError }} — 请检查网络后刷新</div>
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
            <div class="slider-track">
              <div class="slider-fill" :style="{ width: sliderFillPct + '%' }"></div>
            </div>
            <input
              v-model.number="currentYear"
              type="range"
              :min="YEAR_MIN"
              :max="YEAR_MAX"
              step="1"
              class="native-range"
            />
            <div class="slider-ticks">
              <div
                v-for="y in YEARS"
                :key="y"
                class="tick"
                :class="{ active: y === currentYear }"
                @click="currentYear = y"
              >
                {{ String(y).slice(-2) }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 右：图例 + Top10 + 明细 -->
      <aside class="side-panel">
        <div class="card">
          <div class="card-head">
            <h3>风险图例</h3>
            <span class="meta">Y · DETRENDED VOLATILITY</span>
          </div>
          <div class="legend-body">
            <div class="legend-bar">
              <div :style="{ background: 'var(--risk-1)' }"></div>
              <div :style="{ background: 'var(--risk-2)' }"></div>
              <div :style="{ background: 'var(--risk-3)' }"></div>
              <div :style="{ background: 'var(--risk-4)' }"></div>
              <div :style="{ background: 'var(--risk-5)' }"></div>
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
              <span v-else class="v muted">— 起始年</span>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>Top 10 高风险省份</h3>
            <span class="meta">YEAR {{ currentYear }}</span>
          </div>
          <div class="top10-body">
            <div
              v-for="(d, i) in top10"
              :key="d.name"
              class="rank-row"
              :class="{ active: d.name === hoveredProvince }"
              @click="onRowClick(d.name)"
            >
              <span class="rank-num">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="rank-name">{{ d.name }}</span>
              <div class="rank-bar">
                <div
                  class="rank-bar-fill"
                  :style="{
                    width: ((d.y - 0.011) / (0.043 - 0.011)) * 100 + '%',
                    background: riskColorVar(d.y),
                  }"
                ></div>
              </div>
              <span class="rank-val" :style="{ color: riskColorVar(d.y) }">{{ d.y.toFixed(4) }}</span>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>省份明细</h3>
            <span class="meta">{{ detail ? `${currentYear} · ${detail.type}` : 'HOVER / 点击 查看' }}</span>
          </div>
          <div class="detail-body">
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
                  <span>{{ YEAR_MIN }} — {{ YEAR_MAX }}</span>
                </div>
                <div ref="miniEl" class="mini-chart"></div>
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

    <footer class="page-foot">
      <a href="/prototypes/01-risk-map.html" target="_blank" class="proto-link">查看原型 HTML ↗</a>
      <span class="note">Vue 化数据层为前端 mock；接 SQLite 后切真值。模型 R² 数字（XGB 0.9072 / Att-LSTM 0.8160）来自 <code>backend/models/*</code></span>
    </footer>
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
.lead code {
  font-family: var(--font-mono);
  background: var(--bg-elev);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
}

.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(340px, 1fr);
  gap: 20px;
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
.mini-chart { height: 64px; }

.page-foot {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--text-3);
}
.page-foot .note { font-family: var(--font-mono); }
.page-foot .note code {
  background: var(--bg-elev);
  padding: 1px 5px;
  border-radius: 2px;
  font-size: 10px;
}
.proto-link {
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
.proto-link:hover {
  border-color: var(--green);
  transform: translateY(-1px);
}
</style>
