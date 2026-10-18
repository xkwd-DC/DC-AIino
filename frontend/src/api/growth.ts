import http from './http'

export interface GrowthZone {
  key: string
  name: string
  req_gdd: number
  season_days: number
  sowing: string
  kc: number
}

export interface GrowthCounty {
  code: number
  name: string
  province: string
  city: string
  lon: number | null
  lat: number | null
  zone: string
  gdd: number
  ppt: number
  pet: number
  tmax: number
  spei: number
  irr: number
  ndvi: number
  heat_mean: number
  heat_p90: number
  baseline_gsi: number
}

export interface GrowthCountiesData {
  meta: {
    crop: string
    years: [number, number]
    county_count: number
    note: string
  }
  zones: GrowthZone[]
  count: number
  rows: GrowthCounty[]
}

export interface GrowthFactor {
  gsi_abs: number
  gdd: number
  ppt: number
  pet: number
  etc: number
  heat_days: number
  critical_heat: number
  f_gdd: number
  f_water: number
  f_heat: number
  limiting: 'gdd' | 'water' | 'heat' | 'none'
  limiting_label: string
}

export interface GrowthScenario {
  county_code: number
  d_temp: number
  d_prec_pct: number
  d_heat_days: number
  irrigation: number
}

export interface GrowthResult {
  county: {
    code: number
    name: string
    province: string
    city: string
    lon: number | null
    lat: number | null
    zone: string
    zone_name: string
    sowing: string
    req_gdd: number
  }
  params: {
    d_temp: number
    d_prec_pct: number
    d_heat_days: number
    irrigation: number
  }
  baseline: GrowthFactor
  scenario: GrowthFactor
  gsi: number
  delta_pct: number
  percentile: number
  limiting: GrowthFactor['limiting']
  limiting_label: string
  interpretation: string
  metric_note: string
}

export function fetchGrowthCounties(): Promise<GrowthCountiesData> {
  return http.get('/growth/counties')
}

export function postGrowthSimulate(body: GrowthScenario): Promise<GrowthResult> {
  return http.post('/growth/simulate', body)
}
