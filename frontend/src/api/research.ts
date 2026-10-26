import http from './http'

export interface AuditProtocol {
  id: string
  label: string
  r2: number
  sd?: number
  mean?: number
  positive_folds?: number
  folds: number
  reads: string
  source: string
}

export interface AuditFlag {
  level: 'high' | 'medium' | 'low'
  title: string
  evidence: string
  meaning: string
  next: string
}

export interface AuditAblation {
  id: string
  label: string
  with_feature?: number
  without_feature?: number
  delta?: number
  r2?: number
  sd?: number
  reads: string
  source: string
}

export interface ModelCardMeta {
  slug: string
  title: string
  filename: string
  size: number
  updated: string
}

export interface ResearchAudit {
  generated_at: string
  version: string
  headline: string
  boundary: string
  data: {
    panel: string
    rows: number
    provinces: number
    years: string
    target: string
    features: number
    feature_order_source: string
    note: string
  }
  protocols: AuditProtocol[]
  variance: {
    model: string
    icc: number
    icc_ci: [number, number]
    sigma_alpha_sq: number
    sigma_eps_sq: number
    lrt: number
    p_value_chibar: number
    reads: string
    source: string
  }
  attribution: {
    xgb_top3: string[]
    att_top3: string[]
    spearman: number
    p_value: number
    top3_overlap: string
    top5_overlap: string
    reads: string
    source: string
  }
  ablations: AuditAblation[]
  scale: {
    log_total_variance_explained_by_area: number
    climg_lco_r2: number
    climg_lco_sd: number
    climg_time_r2: number
    climg_time_sd: number
    single_yield_lco_r2: number
    single_yield_lco_sd: number
    single_yield_time_r2: number
    reads: string
    source: string
  }
  flags: AuditFlag[]
  cards: ModelCardMeta[]
}

export interface SensitivityPoint {
  x: number
  yield_kg_per_ha: number
  risk: number
  delta_risk: number
}

export interface SensitivityCurve {
  feature: string
  label: string
  unit: string
  baseline: number
  observed_range: [number, number]
  scan_range: [number, number]
  swing: number
  points: SensitivityPoint[]
}

export interface SensitivityResult {
  province: string
  model: string
  method: string
  baseline_yield_kg_per_ha: number
  baseline_risk: number
  curves: SensitivityCurve[]
  note: string
  generated_at: string
}

export function fetchResearchAudit(): Promise<ResearchAudit> {
  return http.get('/research/audit')
}

export function postSensitivity(province: string): Promise<SensitivityResult> {
  return http.post('/research/sensitivity', { province })
}

export function modelCardUrl(slug: string): string {
  return `/api/research/model-cards/${encodeURIComponent(slug)}`
}

export function reproBundleUrl(): string {
  return '/api/research/repro-bundle'
}
