import http from './http'

// ─── 来自 /api/provinces 与 /api/provinces/<name>/history 的真实 schema ───────
// 与 backend/services/panel_repo.py FEATURE_COLS / get_panel_by_year 严格对齐。
//
// 注意:
// - `y` 字段（前端 mock 用的 detrended volatility）后端不直接返回,需要由 view 层
//   用 yield_kg_per_ha + baseline 推算,或在没有 db 数据时 fallback 到 baseline json
//   里的 `y` 字段。两种 schema 由可选字段统一表达,api 层不抛错。
// - 字段名沿用 backend 风格(下划线小写),便于 1:1 对齐。

export interface ProvinceRow {
  /** 省份中文名,如 "河南" */
  name?: string
  /** 仅来自 grain.db 的字段(可选)— 没 db 时是 undefined */
  province?: string
  name_en?: string
  region?: string
  year?: number
  yield_kg_per_ha?: number
  y_butter?: number
  y_linear?: number
  // 通用风险/参数字段 — baseline json 与 grain.db 行都会带
  y?: number
  type?: string
  summary?: string
  irr?: number
  flood?: number   // baseline json 字段
  flood_r?: number // grain.db 字段
  sun?: number
  temp?: number
  spei?: number
  prec?: number
  mech?: number
  fert?: number
  drou_a?: number
  flood_a?: number
  ndvi?: number
}

export interface HistoryEntry {
  year: number
  yield_kg_per_ha: number | null
  y_butter: number | null
  y_linear: number | null
  ndvi: number | null
  temp: number | null
  prec: number | null
  sun: number | null
  spei: number | null
  drou_a: number | null
  flood_a: number | null
  flood_r: number | null
  irr: number | null
  fert: number | null
  mech: number | null
}

export interface ProvinceHistory {
  province: string
  name_en: string
  region: string
  series: HistoryEntry[]
}

/** GET /api/provinces[?year=YYYY] — 31 省面板数据。
 *
 * - 不带 year:返最新年(grain.db 存在时)或 baseline json
 * - 带 year:必须 grain.db 存在,否则后端返 503
 */
export function fetchProvinces(year?: number): Promise<ProvinceRow[]> {
  return http.get('/provinces', { params: year ? { year } : undefined })
}

/** GET /api/provinces/<name>/history — 单省 2011-2023 时序。
 *
 * 仅在 grain.db 存在时可用,否则后端返 503;前端需做错误处理。
 */
export function fetchProvinceHistory(province: string): Promise<ProvinceHistory> {
  // 中文省名走 URL path,axios 默认会 encodeURIComponent。
  return http.get(`/provinces/${encodeURIComponent(province)}/history`)
}
