/**
 * M01 风险地图前端 mock 数据。
 *
 * Phase 4（5/27-28）后会切到后端 SQLite `/api/provinces?year=YYYY` +
 * `/api/provinces/<name>/history`，本文件即可弃用。
 *
 * 数据生成策略沿用 frontend/prototypes/01-risk-map.html § 1 DATA LAYER：
 * 31 省基础锚定值 + 年度气候趋势分量 + 省份特异波动（hash seed 伪随机）。
 */

export interface ProvinceBase {
  name: string
  y: number
  irr: number
  flood: number
  sun: number
  spei: number
  temp: number
  type: string
}

export interface ProvinceSnapshot extends ProvinceBase {}

export const PROVINCES_BASE: ProvinceBase[] = [
  // 西北高风险带
  { name: '青海', y: 0.040, irr: 28, flood: 1.2, sun: 3120, spei: -1.8, temp: 4.5, type: '高寒旱作型' },
  { name: '西藏', y: 0.038, irr: 25, flood: 0.8, sun: 3320, spei: -1.5, temp: 5.2, type: '高寒旱作型' },
  { name: '新疆', y: 0.036, irr: 110, flood: 0.5, sun: 3150, spei: -2.3, temp: 8.6, type: '极端干旱型' },
  { name: '甘肃', y: 0.034, irr: 65, flood: 1.5, sun: 2680, spei: -1.6, temp: 9.5, type: '半干旱型' },
  { name: '宁夏', y: 0.032, irr: 88, flood: 1.1, sun: 2820, spei: -1.4, temp: 9.8, type: '半干旱灌溉型' },
  { name: '内蒙古', y: 0.033, irr: 52, flood: 2.3, sun: 2950, spei: -1.2, temp: 5.8, type: '草原旱作型' },
  { name: '陕西', y: 0.029, irr: 56, flood: 3.8, sun: 2200, spei: -0.6, temp: 13.2, type: '半干旱过渡型' },
  { name: '山西', y: 0.028, irr: 48, flood: 3.2, sun: 2480, spei: -0.9, temp: 11.0, type: '半干旱过渡型' },
  // 西南山地
  { name: '云南', y: 0.027, irr: 38, flood: 5.2, sun: 2180, spei: -0.5, temp: 16.5, type: '山地多灾型' },
  { name: '贵州', y: 0.026, irr: 32, flood: 6.8, sun: 1380, spei: 0.2, temp: 15.4, type: '岩溶多雨型' },
  { name: '四川', y: 0.024, irr: 58, flood: 5.1, sun: 1280, spei: 0.1, temp: 16.8, type: '盆地温润型' },
  { name: '重庆', y: 0.025, irr: 54, flood: 7.2, sun: 1180, spei: 0.4, temp: 18.2, type: '盆地多雨型' },
  { name: '广西', y: 0.027, irr: 62, flood: 9.5, sun: 1620, spei: 0.6, temp: 21.5, type: '南方多洪型' },
  // 中部主产区
  { name: '河南', y: 0.026, irr: 65, flood: 4.2, sun: 2160, spei: -0.1, temp: 14.8, type: '主产区主导型' },
  { name: '湖北', y: 0.023, irr: 68, flood: 7.5, sun: 1820, spei: 0.3, temp: 16.6, type: '中游洪涝型' },
  { name: '湖南', y: 0.024, irr: 72, flood: 8.8, sun: 1620, spei: 0.4, temp: 17.5, type: '中游多雨型' },
  { name: '安徽', y: 0.025, irr: 75, flood: 9.2, sun: 2020, spei: 0.2, temp: 15.8, type: '江淮多洪型' },
  { name: '江西', y: 0.026, irr: 70, flood: 11.5, sun: 1780, spei: 0.5, temp: 18.2, type: '南方多洪型' },
  // 沿海台风
  { name: '广东', y: 0.025, irr: 65, flood: 14.2, sun: 1880, spei: 0.7, temp: 22.5, type: '沿海台风型' },
  { name: '福建', y: 0.026, irr: 58, flood: 18.5, sun: 1820, spei: 0.6, temp: 20.4, type: '沿海台风型' },
  { name: '浙江', y: 0.022, irr: 62, flood: 13.8, sun: 1900, spei: 0.4, temp: 17.6, type: '沿海台风型' },
  { name: '海南', y: 0.024, irr: 48, flood: 22.5, sun: 2080, spei: 0.8, temp: 24.5, type: '热带台风型' },
  { name: '台湾', y: 0.022, irr: 55, flood: 19.2, sun: 1980, spei: 0.5, temp: 22.8, type: '热带台风型' },
  // 华北平原
  { name: '河北', y: 0.022, irr: 78, flood: 3.5, sun: 2540, spei: -0.5, temp: 12.5, type: '主产区主导型' },
  { name: '山东', y: 0.021, irr: 82, flood: 4.1, sun: 2480, spei: -0.3, temp: 13.6, type: '主产区主导型' },
  { name: '天津', y: 0.020, irr: 88, flood: 3.2, sun: 2580, spei: -0.4, temp: 12.8, type: '城郊型' },
  { name: '江苏', y: 0.021, irr: 90, flood: 6.8, sun: 2120, spei: 0.0, temp: 15.5, type: '主产区主导型' },
  // 低风险
  { name: '北京', y: 0.018, irr: 92, flood: 2.8, sun: 2620, spei: -0.4, temp: 12.6, type: '城郊低风险型' },
  { name: '上海', y: 0.019, irr: 95, flood: 5.5, sun: 1980, spei: 0.1, temp: 16.2, type: '城郊低风险型' },
  { name: '黑龙江', y: 0.020, irr: 35, flood: 2.5, sun: 2580, spei: -0.6, temp: 2.6, type: '寒地大田型' },
  { name: '吉林', y: 0.023, irr: 42, flood: 2.8, sun: 2580, spei: -0.4, temp: 5.6, type: '寒地大田型' },
  { name: '辽宁', y: 0.022, irr: 56, flood: 3.6, sun: 2420, spei: -0.3, temp: 8.8, type: '东北边缘型' },
]

export const YEARS = Array.from({ length: 13 }, (_, i) => 2011 + i)
export const YEAR_MIN = 2011
export const YEAR_MAX = 2023

export const RANGES = {
  y: [0.011, 0.045] as [number, number],
  irr: [20, 120] as [number, number],
  flood: [0, 24] as [number, number],
  sun: [970, 3350] as [number, number],
  spei: [-3, 3] as [number, number],
  temp: [2, 26] as [number, number],
}

function hashStr(s: string): number {
  let h = 0
  for (const c of s) h = ((h << 5) - h + c.charCodeAt(0)) | 0
  return Math.abs(h)
}

function seededRandom(seed: number): () => number {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}

function makeYearSnapshot(p: ProvinceBase, year: number): ProvinceSnapshot {
  const seed = hashStr(p.name) + year * 17
  const rng = seededRandom(seed)
  const yIdx = year - YEAR_MIN

  const trend = yIdx < 7 ? -0.001 + yIdx * 0.0002 : 0.0006 + (yIdx - 7) * 0.0008
  const noise = (rng() - 0.5) * 0.30 * p.y

  return {
    name: p.name,
    type: p.type,
    y: clamp(p.y + trend + noise, 0.011, 0.045),
    irr: clamp(p.irr + (rng() - 0.5) * 6, 20, 120),
    flood: clamp(p.flood + (rng() - 0.5) * 3, 0, 24),
    sun: clamp(p.sun + (rng() - 0.5) * 200, 970, 3350),
    spei: clamp(p.spei + (rng() - 0.5) * 0.5, -3, 3),
    temp: p.temp + (rng() - 0.5) * 0.8,
  }
}

export const ALL_DATA: Record<number, ProvinceSnapshot[]> = YEARS.reduce(
  (acc, year) => {
    acc[year] = PROVINCES_BASE.map((p) => makeYearSnapshot(p, year))
    return acc
  },
  {} as Record<number, ProvinceSnapshot[]>,
)

export function percentile(val: number, range: [number, number]): number {
  return clamp(((val - range[0]) / (range[1] - range[0])) * 100, 0, 100)
}

export function riskColorVar(y: number): string {
  if (y < 0.018) return 'var(--risk-1)'
  if (y < 0.024) return 'var(--risk-2)'
  if (y < 0.030) return 'var(--risk-3)'
  if (y < 0.036) return 'var(--risk-4)'
  return 'var(--risk-5)'
}

export function getCSSVar(name: string): string {
  if (typeof window === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function riskColorResolved(y: number): string {
  if (y < 0.018) return getCSSVar('--risk-1')
  if (y < 0.024) return getCSSVar('--risk-2')
  if (y < 0.030) return getCSSVar('--risk-3')
  if (y < 0.036) return getCSSVar('--risk-4')
  return getCSSVar('--risk-5')
}
