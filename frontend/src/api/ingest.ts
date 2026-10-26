import http from './http'

// ─── M08 数据整备 API(/api/ingest*) ──────────────────────────────────────────
//
// 这条链路只做「对齐 + 质检 + 导出」，不写主库、不调模型。
// 国外模式要读本地 TerraClimate 栅格，单次可能跑 20s 以上，所以单独放宽超时。

export type IngestMode = 'china' | 'custom'

export interface FieldSpec {
  key: string
  label: string
  kind: string
  required: boolean
}

export interface MappingItem {
  column: string | null
  confidence: number
  matched_alias: string
}

export type Mapping = Record<string, MappingItem>

export interface UnitHint {
  suggested: string
  reason: string
  median: number
}

export interface SessionCreated {
  session_id: string
  mode: IngestMode
  source_file: string
  rows: number
  columns: string[]
  years: number[]
  mapping: Mapping
  units: { chosen: Record<string, string>; inferred: Record<string, UnitHint> }
  field_specs: FieldSpec[]
  unit_options: Record<string, Record<string, number>>
  preview: Array<Record<string, unknown>>
}

export type FindingLevel = 'blocker' | 'warning' | 'info'

export interface Finding {
  level: FindingLevel
  rule: string
  title: string
  detail: string
  count: number
  samples: string[]
  suggestion: string
}

export interface RunSummary {
  generated_at: string
  source_file: string
  input_rows: number
  output_rows: number
  mode: IngestMode
  matched: number
  match_rate: number
  match_method: Record<string, number>
  climate_covered: number
  climate_rate: number
  geo_units?: number
}

export interface ExportItem {
  kind: 'csv' | 'report' | 'script'
  label: string
  hint: string
}

export interface RunResult {
  session_id: string
  summary: RunSummary
  findings: Finding[]
  blocked: boolean
  columns: string[]
  preview: Array<Record<string, unknown>>
  exports: ExportItem[]
}

/** 上传统计表（国外模式还需地理文件）。超过 10 MB 后端直接 413。 */
export function createIngestSession(payload: {
  mode: IngestMode
  stats: File
  geo?: File | null
}): Promise<SessionCreated> {
  const form = new FormData()
  form.append('mode', payload.mode)
  form.append('stats', payload.stats)
  if (payload.geo) form.append('geo', payload.geo)
  return http.post('/ingest/sessions', form, {
    timeout: 120000,
    headers: { 'Content-Type': 'multipart/form-data' },
  }) as Promise<SessionCreated>
}

/** 按确认后的映射与单位执行清洗。国外模式读栅格，超时给足 180s。 */
export function runIngest(
  sessionId: string,
  payload: { mapping: Mapping; units: Record<string, string> },
): Promise<RunResult> {
  return http.post(`/ingest/sessions/${sessionId}/run`, payload, {
    timeout: 180000,
  }) as Promise<RunResult>
}

/** 导出文件走浏览器直链，避免 axios 处理二进制。 */
export function exportUrl(sessionId: string, kind: ExportItem['kind']): string {
  return `/api/ingest/sessions/${sessionId}/export/${kind}`
}
