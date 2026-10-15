import http from './http'

// ─── 县级层 API(/api/counties*)。与省级 /api/provinces 是两套独立口径 ──────────
//
// 口径要点(见 backend/models/county_climg_card.md):
// - 县级模型的特征是**剔除规模与省-年常量后的纯气候 16 维**(CLIMG),目标 log(粮食总产量);
// - `risk_level` / `risk_pct` 取自 `clim_anomaly`(县内去均值后的当年气候偏离,逐年可比);
// - `clim_contrib` / `contrib_pct` 是气候条件画像(跨县可比,含县际结构差异),只作明细展示。

export type UnitType = 'farm' | 'urban' | 'unknown'
export type UnitFilter = 'all' | 'farm'

/** 县级快照行。一年约 1,200 行，故只含地图与清单所需字段；
 *  单县的完整轨迹与 16 维归因由 fetchCountyHistory / fetchCountyAttribution 提供。 */
export interface CountyRow {
  county_code: number
  county: string
  province: string
  /** 与 /maps/counties_10provinces.json 的 properties.name 同口径,地图按它着色 */
  map_key: string
  /** 该县是否有县级边界可渲染(v7 面板含县域年鉴的"市辖区"合计行,这类没有独立边界) */
  on_map: boolean
  risk_level: number
  risk_pct: number
  clim_anomaly: number
  unit_type: UnitType
  grain_output_t: number | null
}

export interface CountyList {
  year: number
  unit: UnitFilter
  count: number
  rows: CountyRow[]
}

export interface CountyHistoryEntry {
  year: number
  y_true: number | null
  y_pred: number | null
  clim_contrib: number
  clim_anomaly: number
  risk_level: number
  risk_pct: number
  contrib_pct: number
  unit_type: UnitType
  grain_output_t: number | null
  sown_kha: number | null
  temp: number | null
  prec: number | null
  sun: number | null
  gs_tmax_mean: number | null
  gs_ppt: number | null
  gs_prec_share: number | null
  spei_growing_season_mean: number | null
}

export interface CountyHistory {
  county: {
    county_code: number
    county: string
    city: string | null
    province: string
    lon: number | null
    lat: number | null
    map_key: string
    on_map: boolean
  }
  series: CountyHistoryEntry[]
}

export interface CountySummary {
  scored_rows: number
  truth_rows: number
  unscored_rows: number
  farm_rows: number
  counties: number
  years: number[]
  /** 逐年的样本覆盖：scored = 有气候可打分的县年，truth = 其中有产量真值的 */
  year_coverage: Array<{ year: number; scored: number; truth: number }>
  provinces: Array<{ province: string; n: number }>
  meta: Record<string, string | null>
  climate_features: string[]
  agri_output_threshold_t: number
  risk_index_definition: string | null
}

export interface LadderRow {
  level: string
  scope: string
  lco_r2: string
  time_r2: string
  reading: string
  source: string
}

export interface NullRow {
  config: string
  n_feat: string
  true_mean: string | null
  null_mean: string | null
  excess: string | null
  frac_true_gt_null: string | null
}

export interface CountyStandard {
  ladder: LadderRow[]
  /** permutation 阴性对照：真实 R² vs 逐列打乱后的 null 分布 */
  nulls: NullRow[]
  /** 规模口径诊断：log(总产量) 有多少方差其实是播种面积贡献的 */
  scale_diagnosis: Record<string, string>
  scale_note: string | null
  bootstrap: Record<string, string>
  note: string
}

export interface AttributionItem {
  feature: string
  label: string
  unit: string
  family: 'annual' | 'seasonal'
  /** 该维的 SHAP 边际贡献(Δlog 总产量) */
  shap: number | null
  /** 该维当年的实际取值 */
  value: number | null
  /** 训练期与测试期 SHAP 方向是否同号(null = 无该维证据) */
  direction_stable: boolean | null
}

export interface CountyAttribution {
  county: CountyHistory['county']
  year: number
  available: boolean
  summary?: {
    clim_contrib: number
    clim_anomaly: number
    y_pred: number | null
    y_true: number | null
    risk_level: number
    risk_pct: number
    contrib_pct: number
    unit_type: UnitType
  }
  items: AttributionItem[]
}

/** GET /api/counties[?year=&unit=&province=] — 某年县级快照。缺 year 时后端给最新年。 */
export function fetchCounties(params: {
  year?: number
  unit?: UnitFilter
  province?: string
}): Promise<CountyList> {
  return http.get('/counties', {
    params: {
      ...(params.year ? { year: params.year } : {}),
      ...(params.unit && params.unit !== 'all' ? { unit: params.unit } : {}),
      ...(params.province ? { province: params.province } : {}),
    },
  })
}

/** GET /api/counties/meta/summary — 覆盖率与元信息。 */
export function fetchCountySummary(): Promise<CountySummary> {
  return http.get('/counties/meta/summary')
}

/** GET /api/counties/meta/standard — 空间粒度递进与协议数字(前端不写死任何数字)。 */
export function fetchCountyStandard(): Promise<CountyStandard> {
  return http.get('/counties/meta/standard')
}

/** GET /api/counties/<code>/history — 单县 2012-2023 轨迹。 */
export function fetchCountyHistory(code: number): Promise<CountyHistory> {
  return http.get(`/counties/${code}/history`)
}

/** GET /api/counties/<code>/attribution?year= — 单县单年 16 维气候边际贡献。 */
export function fetchCountyAttribution(code: number, year: number): Promise<CountyAttribution> {
  return http.get(`/counties/${code}/attribution`, { params: { year } })
}
