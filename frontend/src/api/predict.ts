import http from './http'

// ─── 请求参数类型 ────────────────────────────────────────────────────────────
export interface PredictParams {
  irr?: number
  flood?: number
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

export type PredictModel = 'xgboost' | 'lstm' | 'ensemble'

// ─── 响应 schema (对齐 backend/api/predict.py L397-411) ─────────────────────
export interface ShapContrib {
  feature: string
  value: number
  direction: 'harm' | 'protect'
}

export interface Recommendation {
  action: string
  factor: string
  expected_delta: number
  priority: 'high' | 'medium' | 'low'
}

export interface PredictData {
  province: string
  year: number | null
  model: string
  baseline: number
  delta: number
  confidence: number
  risk_score: number
  // ensemble only
  xgboost_risk?: number
  lstm_risk?: number
  att_lstm_risk?: number
  consensus?: number
  divergence?: number
  xgboost_yield_kg_per_ha?: number
  lstm_yield_kg_per_ha?: number
  att_lstm_yield_kg_per_ha?: number
  // single-model only
  yield_kg_per_ha?: number
  shap_top: ShapContrib[]
  recommendations: Recommendation[]
  params_used: Record<string, number>
  params_filled_from_baseline: string[]
  _mock: boolean
}

// ─── 200ms 防抖工具（轻量，避免引入 lodash）────────────────────────────────
function debounce<F extends (...args: never[]) => void>(fn: F, ms: number): F {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: Parameters<F>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }) as F
}

// ─── 核心请求函数 ─────────────────────────────────────────────────────────
/** POST /api/predict。http 拦截器已解包 envelope，直接返回 data 字段。 */
export function postPredict(
  province: string,
  params: PredictParams,
  model: PredictModel = 'ensemble',
): Promise<PredictData> {
  return http.post('/predict', { province, params, model })
}

/** 带 200ms 防抖的 postPredict（给 ScenarioSim 滑块场景使用）。
 *  注意：防抖版本传入回调，不返回 Promise，因为 debounce 本身是 fire-and-forget。
 *  调用方负责在回调中更新响应式状态。
 */
export const postPredictDebounced = debounce(
  (
    province: string,
    params: PredictParams,
    model: PredictModel,
    onSuccess: (data: PredictData) => void,
    onError: (err: unknown) => void,
  ) => {
    postPredict(province, params, model).then(onSuccess).catch(onError)
  },
  200,
)
