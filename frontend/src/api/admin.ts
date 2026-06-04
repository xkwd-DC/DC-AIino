/**
 * Admin / 推演监控相关接口客户端
 *
 * 当前仅有 GET /api/admin/predicts —— 拉取最近 N 次 /api/predict trace,
 * 供 M05 推演监控面板渲染。
 *
 * Trace schema 严格对齐 backend/api/predict.py 中 `trace = {...}` 字面量。
 * 单模型(xgboost / lstm)调用时 ensemble-only 字段为 undefined;
 * ensemble 调用时 single-only 的 yield_kg_per_ha 为 undefined。
 */
import http from './http'
import type { ShapContrib, Recommendation } from './predict'

/** 一次 /api/predict 调用的完整 trace。 */
export interface PredictTrace {
  ts: string                              // ISO8601 UTC
  province: string
  model: 'xgboost' | 'lstm' | 'ensemble'
  params: Record<string, number>          // 11 维 (round 4)
  params_filled_from_baseline: string[]   // 由 baseline 补全的 key 列表
  baseline: number                        // 该省 baseline.y
  delta: number                           // risk_score - baseline
  risk_score: number                      // 最终 risk(单模型 = 该模型;ensemble = consensus)
  // ensemble only
  xgboost_risk?: number | null
  lstm_risk?: number | null
  att_lstm_risk?: number | null
  xgboost_yield_kg_per_ha?: number | null
  lstm_yield_kg_per_ha?: number | null
  att_lstm_yield_kg_per_ha?: number | null
  consensus?: number | null
  divergence?: number | null
  // single-model only
  yield_kg_per_ha?: number | null
  shap_top: ShapContrib[]
  recommendations: Recommendation[]
  latency_ms: number
}

export interface PredictHistoryData {
  count: number
  max: number
  items: PredictTrace[]    // 最新在前
}

export function fetchPredictHistory(): Promise<PredictHistoryData> {
  return http.get('/admin/predicts')
}
