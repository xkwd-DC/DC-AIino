<script setup lang="ts">
/**
 * M07 · 县级风险地图(县级面板层)。
 *
 * 这是站点从省级(31 省 × 13 年 = 403 行)下沉到县级(1,199 县 × 12 年 = 14,388 行)的
 * 新模块。视图只做"取数 + 编排",渲染拆给三个子组件:
 *   CountyMap         地图着色与选县
 *   CountyDetail      选中县明细(逐年轨迹 + 当年归因)
 *   GranularityLadder 口径与迁移体检(前端不写死任何数字)
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  fetchCounties,
  fetchCountyAttribution,
  fetchCountyHistory,
  fetchCountyStandard,
  fetchCountySummary,
  type CountyAttribution,
  type CountyHistoryEntry,
  type CountyRow,
  type CountyStandard,
  type CountySummary,
  type UnitFilter,
} from '@/api/county'
import CountyMap from '@/components/county/CountyMap.vue'
import CountyDetail from '@/components/county/CountyDetail.vue'
import GranularityLadder from '@/components/county/GranularityLadder.vue'

const RISK_LABELS = ['低', '较低', '中等', '较高', '高']

const summary = ref<CountySummary | null>(null)
const standard = ref<CountyStandard | null>(null)
const standardError = ref<string | null>(null)
const standardLoading = ref(true)

const rows = ref<CountyRow[]>([])
const rowsLoading = ref(false)
const rowsError = ref<string | null>(null)

const year = ref<number | null>(null)
const unit = ref<UnitFilter>('all')
const province = ref<string>('')

const selectedCode = ref<number | null>(null)
const historySeries = ref<CountyHistoryEntry[]>([])
const historyMeta = ref<Awaited<ReturnType<typeof fetchCountyHistory>>['county'] | null>(null)
const detailLoading = ref(false)
const detailError = ref<string | null>(null)
const attribution = ref<CountyAttribution | null>(null)

const years = computed(() => summary.value?.years ?? [])
const provinces = computed(() => summary.value?.provinces ?? [])
const yearMin = computed(() => years.value[0] ?? 2012)
const yearMax = computed(() => years.value[years.value.length - 1] ?? 2023)

const sliderFillPct = computed(() => {
  if (year.value == null || yearMax.value === yearMin.value) return 100
  return ((year.value - yearMin.value) / (yearMax.value - yearMin.value)) * 100
})

/** 高风险县 Top 10:风险等级降序 + 年内分位升序。同时充当地图的文字替代。 */
const top10 = computed(() =>
  [...rows.value]
    .sort((a, b) => b.risk_level - a.risk_level || a.risk_pct - b.risk_pct)
    .slice(0, 10),
)

const levelCounts = computed(() => {
  const counts = [0, 0, 0, 0, 0]
  for (const r of rows.value) counts[r.risk_level - 1] += 1
  return counts
})

const scopeText = computed(() => {
  const s = summary.value
  if (!s) return ''
  const shown = rows.value.length
  return `当前显示 ${shown} 个单元 · 面板共 ${s.counties} 县 / ${s.scored_rows} 个县年` +
    `（有产量真值 ${s.truth_rows}）· ${s.climate_features.length} 维气候特征`
})

/** 当年覆盖情况。2023 年面板整体无产量真值（县域统计年鉴 2024 卷未出版），
 *  该年的气候贡献是纯外推，必须在界面上说清楚，不能让人当成"已验证的风险"。 */
const coverage = computed(() => {
  if (year.value == null || !summary.value) return null
  return summary.value.year_coverage.find((c) => c.year === year.value) ?? null
})

const coverageNote = computed(() => {
  const c = coverage.value
  const scored = c?.scored ?? 0
  const truth = c?.truth ?? 0
  if (scored === 0) return { level: 'warn' as const, text: '该年无面板数据' }
  if (truth === 0) {
    return {
      level: 'warn' as const,
      text: `${year.value} 年面板无产量真值（县域统计年鉴 2024 卷未出版）：本页气候贡献为模型外推，只可读"气候条件"，不可读"已核实的风险"。`,
    }
  }
  const pct = Math.round((truth / scored) * 100)
  return { level: 'ok' as const, text: `该年有产量真值 ${truth} / ${scored} 个县年（${pct}%）` }
})

async function loadRows() {
  if (year.value == null) return
  rowsLoading.value = true
  rowsError.value = null
  try {
    const data = await fetchCounties({
      year: year.value,
      unit: unit.value,
      province: province.value || undefined,
    })
    rows.value = data.rows
    // 首屏不要留一个空白明细卡:默认落到当年最高风险的县(用户点选后不再自动改)
    if (selectedCode.value == null && rows.value.length > 0) {
      const top = [...rows.value].sort(
        (a, b) => b.risk_level - a.risk_level || a.risk_pct - b.risk_pct,
      )[0]
      selectedCode.value = top.county_code
    }
  } catch (e) {
    rows.value = []
    rowsError.value = e instanceof Error ? e.message : '县级面板加载失败'
  } finally {
    rowsLoading.value = false
  }
}

async function loadDetail(code: number) {
  detailLoading.value = true
  detailError.value = null
  try {
    const data = await fetchCountyHistory(code)
    historyMeta.value = data.county
    historySeries.value = data.series
  } catch (e) {
    historyMeta.value = null
    historySeries.value = []
    detailError.value = e instanceof Error ? e.message : '该县数据读取失败'
  } finally {
    detailLoading.value = false
  }
}

async function loadAttribution(code: number, y: number) {
  try {
    attribution.value = await fetchCountyAttribution(code, y)
  } catch {
    // 归因是加强信息,取不到不影响明细主体
    attribution.value = null
  }
}

function selectCounty(code: number) {
  if (selectedCode.value === code) return
  selectedCode.value = code
}

onMounted(async () => {
  try {
    summary.value = await fetchCountySummary()
    // 默认落在**最新有产量真值的年**：面板末年往往只有气候、没有产量，
    // 直接落在那儿会把整页的归因变成纯外推。
    const withTruth = summary.value.year_coverage.filter((c) => c.truth > 0)
    year.value = withTruth.length
      ? withTruth[withTruth.length - 1].year
      : summary.value.years[summary.value.years.length - 1] ?? null
  } catch (e) {
    rowsError.value = e instanceof Error ? e.message : '县级面板元信息读取失败'
  }

  fetchCountyStandard()
    .then((d) => { standard.value = d })
    .catch((e: unknown) => {
      standardError.value = e instanceof Error ? e.message : '口径表读取失败'
    })
    .finally(() => { standardLoading.value = false })

  await loadRows()
})

watch([year, unit, province], () => { void loadRows() })
watch(selectedCode, (code) => {
  attribution.value = null
  if (code == null) {
    historyMeta.value = null
    historySeries.value = []
    return
  }
  void loadDetail(code)
})
watch([selectedCode, year], ([code, y]) => {
  if (code != null && y != null) void loadAttribution(code, y)
})
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M07 · COUNTY-LEVEL RISK MAP</div>
      <h2>县级风险地图</h2>
      <p class="lead">
        面板从省级（31 省 × 13 年 = 403 行）下沉到县级（10 主产省 1,199 县 × 12 年 = 14,388 行）。
        这一层的模型只吃气候特征 —— 已剔除播种面积/规模与省-年共享常量 ——
        所以它回答的是「气候条件对县级产量的边际贡献」，而不是产量水平预测。
      </p>
    </header>

    <div v-if="rowsError" class="page-banner" role="alert" aria-live="assertive">
      <span class="banner-icon" aria-hidden="true">⚠</span>
      <div class="banner-text">
        <b>{{ rowsError }}</b>
        <button type="button" class="banner-retry" @click="loadRows">重新加载</button>
      </div>
    </div>

    <div class="toolbar">
      <div class="tool-group">
        <div class="tool-label" id="year-label">年份</div>
        <div class="slider-wrap">
          <div class="slider-track" aria-hidden="true">
            <div class="slider-fill" :style="{ width: sliderFillPct + '%' }"></div>
          </div>
          <input
            v-model.number="year"
            type="range"
            class="native-range"
            :min="yearMin"
            :max="yearMax"
            step="1"
            aria-labelledby="year-label"
            :aria-valuemin="yearMin"
            :aria-valuemax="yearMax"
            :aria-valuenow="year ?? yearMax"
            :aria-valuetext="`${year ?? yearMax} 年`"
          />
        </div>
        <output class="year-out mono">{{ year ?? '—' }}</output>
      </div>

      <div class="tool-group">
        <label class="tool-label" for="unit-select">单元口径</label>
        <select id="unit-select" v-model="unit" class="select">
          <option value="all">全部单元</option>
          <option value="farm">仅主产单元</option>
        </select>
      </div>

      <div class="tool-group">
        <label class="tool-label" for="province-select">省份</label>
        <select id="province-select" v-model="province" class="select">
          <option value="">全部</option>
          <option v-for="p in provinces" :key="p.province" :value="p.province">
            {{ p.province }}（{{ p.n }}）
          </option>
        </select>
      </div>

      <p class="scope mono">{{ scopeText }}</p>
    </div>

    <p
      v-if="coverageNote"
      class="coverage"
      :class="coverageNote.level"
      role="status"
      aria-live="polite"
    >
      <span aria-hidden="true">{{ coverageNote.level === 'warn' ? '⚠' : '·' }}</span>
      {{ coverageNote.text }}
    </p>

    <div class="grid">
      <section class="map-panel" aria-labelledby="map-title">
        <div class="panel-head">
          <span class="num mono">M07-A</span>
          <h3 id="map-title">县级气候风险分布</h3>
          <span v-if="rowsLoading" class="status" role="status" aria-live="polite">刷新中…</span>
        </div>
        <CountyMap
          :rows="rows"
          :selected-code="selectedCode"
          :loading="rowsLoading"
          :error="rowsError"
          @select="selectCounty"
        />
        <div class="legend" role="list" aria-label="风险等级色阶">
          <span
            v-for="(label, i) in RISK_LABELS"
            :key="label"
            class="legend-item"
            role="listitem"
          >
            <i class="swatch" :style="{ background: `var(--risk-${i + 1})` }" aria-hidden="true"></i>
            L{{ i + 1 }} {{ label }}
            <span class="mono">{{ levelCounts[i] }}</span>
          </span>
          <span class="legend-item muted">
            <i class="swatch nodata" aria-hidden="true"></i>无数据
          </span>
        </div>
      </section>

      <CountyDetail
        :meta="historyMeta"
        :series="historySeries"
        :attribution="attribution"
        :year="year ?? yearMax"
        :loading="detailLoading"
        :error="detailError"
      />
    </div>

    <section class="top-list" aria-labelledby="county-top-list-desc">
      <h3 id="county-top-list-desc">
        {{ year }} 年高风险县 Top 10
        <span class="mono">（地图的文字替代，可用键盘选择）</span>
      </h3>
      <ol>
        <li v-for="row in top10" :key="row.county_code">
          <button
            type="button"
            class="county-btn"
            :aria-pressed="selectedCode === row.county_code"
            @click="selectCounty(row.county_code)"
          >
            <span class="cname">{{ row.province }} · {{ row.county }}</span>
            <span class="mono">L{{ row.risk_level }} · Δ {{ row.clim_anomaly.toFixed(3) }}</span>
            <span v-if="row.unit_type === 'urban'" class="flag">非主产单元</span>
          </button>
        </li>
      </ol>
      <p v-if="top10.length === 0" class="muted">当前筛选下没有可展示的县。</p>
    </section>

    <GranularityLadder
      :standard="standard"
      :loading="standardLoading"
      :error="standardError"
    />
  </section>
</template>

<style scoped>
.page {
  padding: var(--sp-6) var(--sp-6) var(--sp-8);
  max-width: 1600px;
  margin: 0 auto;
  animation: fadeUp var(--dur-slow) var(--ease-out);
}
.page-head { margin-bottom: var(--sp-5); max-width: 900px; }
.eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.4px;
  color: var(--text-3);
  text-transform: uppercase;
}
h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 600;
  margin: var(--sp-2) 0 var(--sp-3);
}
.lead { font-size: 13px; color: var(--text-2); }
.mono { font-family: var(--font-mono); }
.muted { color: var(--text-3); }

.page-banner {
  display: flex;
  gap: var(--sp-3);
  align-items: center;
  background: rgba(184, 111, 77, 0.12);
  border: 1px solid rgba(184, 111, 77, 0.35);
  border-radius: var(--r-md);
  padding: var(--sp-3) var(--sp-4);
  margin-bottom: var(--sp-4);
  font-size: 12px;
}
.banner-icon { color: var(--amber-bright); }
.banner-text { display: flex; gap: var(--sp-3); align-items: center; flex-wrap: wrap; }
.banner-retry {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--green-bright);
  border: 1px solid rgba(160, 183, 133, 0.35);
  border-radius: var(--r-sm);
  padding: 2px 8px;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-5);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--sp-4) var(--sp-5);
  margin-bottom: var(--sp-5);
}
.tool-group { display: flex; align-items: center; gap: var(--sp-3); }
.tool-label { font-size: 11px; color: var(--text-3); white-space: nowrap; }
.slider-wrap { position: relative; width: 200px; height: 20px; display: flex; align-items: center; }
.slider-track {
  position: absolute;
  left: 0; right: 0;
  height: 3px;
  background: var(--border-strong);
  border-radius: 2px;
}
.slider-fill {
  height: 100%;
  background: var(--green);
  border-radius: 2px;
}
.native-range {
  position: relative;
  width: 100%;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  height: 20px;
}
.native-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: var(--green-bright);
  border: 2px solid var(--bg);
  cursor: pointer;
}
.native-range::-moz-range-thumb {
  width: 14px; height: 14px;
  border-radius: 50%;
  background: var(--green-bright);
  border: 2px solid var(--bg);
  cursor: pointer;
}
.year-out { font-size: 14px; color: var(--green-bright); min-width: 34px; }
.select {
  background: var(--bg-elev);
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  padding: 4px 8px;
  font-family: inherit;
  font-size: 12px;
}
.scope { font-size: 10.5px; color: var(--text-3); margin-left: auto; }

.coverage {
  font-size: 11.5px;
  color: var(--text-2);
  border-left: 2px solid var(--border-strong);
  padding-left: var(--sp-3);
  margin: calc(var(--sp-5) * -1 + var(--sp-2)) 0 var(--sp-5);
}
.coverage.warn {
  color: var(--amber-bright);
  border-left-color: var(--amber);
}

.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.72fr) minmax(320px, 1fr);
  gap: var(--sp-5);
  align-items: stretch;
  margin-bottom: var(--sp-5);
}
.map-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--sp-4) var(--sp-4) var(--sp-3);
  display: flex;
  flex-direction: column;
}
.panel-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-2);
}
.panel-head .num { font-size: 10px; color: var(--text-3); letter-spacing: 1px; }
.panel-head h3 { font-family: var(--font-serif); font-size: 14px; font-weight: 600; }
.status { font-family: var(--font-mono); font-size: 11px; color: var(--text-3); margin-left: auto; }

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-4);
  padding-top: var(--sp-3);
  font-size: 11px;
  color: var(--text-2);
}
.legend-item { display: inline-flex; align-items: center; gap: var(--sp-2); }
.legend-item .mono { font-size: 10px; color: var(--text-3); }
.swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.swatch.nodata { background: var(--bg-elev); border: 1px solid var(--border-strong); }

.top-list {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--sp-5);
  margin-bottom: var(--sp-5);
}
.top-list h3 {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 600;
  margin-bottom: var(--sp-4);
}
.top-list h3 .mono { font-family: var(--font-mono); font-size: 10.5px; color: var(--text-3); font-weight: 400; }
.top-list ol {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--sp-2);
}
.county-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  text-align: left;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: 12px;
  color: var(--text-2);
  transition: border-color var(--dur-fast), background var(--dur-fast);
}
.county-btn:hover { border-color: var(--border-strong); background: var(--bg-elev); }
.county-btn[aria-pressed='true'] {
  border-color: var(--green-bright);
  background: rgba(160, 183, 133, 0.12);
  color: var(--text);
}
.county-btn .cname { flex: 1; }
.county-btn .mono { font-family: var(--font-mono); font-size: 11px; color: var(--text-3); }
.county-btn .flag {
  font-size: 10px;
  color: var(--amber-bright);
  border: 1px solid rgba(230, 182, 85, 0.35);
  border-radius: var(--r-sm);
  padding: 0 4px;
}

@media (max-width: 1180px) {
  .grid { grid-template-columns: minmax(0, 1fr); }
  .scope { margin-left: 0; }
}
@media (max-width: 700px) {
  .page { padding: var(--sp-4) var(--sp-3) var(--sp-7); }
  .toolbar { gap: var(--sp-3); }
  .slider-wrap { width: 140px; }
}
</style>
