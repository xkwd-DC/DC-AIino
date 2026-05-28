/**
 * SHAP 子集聚合 API 客户端
 *
 * 对应 backend GET /api/shap/subset?key={all|north|south|major}
 *
 * 语义:对 subset 内所有省份用 baseline params 调 _approx_contribs,把
 * abs 贡献按特征求和后归一化,作为该子集的"全局重要性"。聚合后 sign 已无
 * 单方向意义,direction 一律返 'neutral',前端 bar chart 用中性色或继续
 * harm/protect 但不强调信号方向。
 *
 * 性能注释:首次请求某 subset 后端 ~3-5s 冷启动(N 省 × 11 次 XGB
 * predict),后续 cache 命中 instant。前端因此应在 selector 切换时显示
 * loading 状态。
 */
import http from './http'

export type SubsetKey = 'all' | 'north' | 'south' | 'major'

/** 单个特征在子集聚合层面的 importance + 原始 mean(|SHAP|)。
 *
 * - importance: 0-1, 已按 sum 归一(全 11 维 sum ≈ 1.0)
 * - mean_abs:   原始 mean(|SHAP|), 跨省平均, tooltip 展示
 * - direction:  'neutral' (聚合后 sign 无意义);保留 harm/protect 兼容性
 */
export interface SubsetFeature {
  feature: string
  importance: number
  mean_abs: number
  direction: 'harm' | 'protect' | 'neutral'
}

export interface ShapSubset {
  subset: SubsetKey
  label: string                  // e.g. "全样本 (31 省)"
  province_count: number
  features: SubsetFeature[]      // 已按 importance 降序, 全 11 维
}

/** GET /api/shap/subset?key=...。http 拦截器已解 envelope,直接返 data。 */
export function fetchShapSubset(key: SubsetKey): Promise<ShapSubset> {
  return http.get(`/shap/subset?key=${encodeURIComponent(key)}`)
}
