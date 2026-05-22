import http from './http'

export interface Province {
  name: string
  y: number
  type: string
  summary: string
  irr: number
  flood: number
  sun: number
  temp: number
  spei: number
  prec: number
  mech: number
  fert: number
  drou_a: number
  flood_a: number
  ndvi: number
}

export function fetchProvinces(year?: number): Promise<Province[]> {
  return http.get('/provinces', { params: year ? { year } : undefined })
}
