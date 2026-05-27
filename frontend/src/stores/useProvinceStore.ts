/**
 * 统一省份状态 store(全前端 source-of-truth)
 *
 * 历史包袱
 * ========
 * - ScenarioSim 与 ResiliencePath 之前各自 `selectedIdx = ref(findIndex('河南'))`,
 *   两个 view 之间选择不同步;PROVINCES_BASE / ALL_DATA 排序口径有歧义。
 * - 本 store 是真后端切换前唯一动这一处即可的位置。
 *
 * 切真后(2026-05-27)
 * ==================
 * - 数据源:`/api/provinces?year=<n>` 返 31 省 + 指定年风险/特征,
 *   `/api/provinces/<name>/history` 返单省 2011-2023 时序。
 * - mock(`mockProvinces.PROVINCES_BASE`)仅作为加载/失败时的骨架 fallback,
 *   不再参与正常渲染。
 * - 加载/失败状态外露,view 层负责 loading skeleton + error + retry UI。
 *
 * 规则引擎(M04)的兼容
 * ====================
 * `recommendation.ts` 仍按 `ProvinceProfile`(继承自 `ProvinceBase`)做规则匹配,
 * 因此 store 暴露的 `provinces` 数组里的每一行都被规整成同样的字段:
 *   { name, y, irr, flood, sun, spei, temp, type }
 * 字段映射在 `normalizeRow()` 里统一处理(grain.db 的 `flood_r` 对应 mock 的 `flood`)。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchProvinces, type ProvinceRow } from '@/api/province'
import { PROVINCES_BASE, type ProvinceBase } from '@/data/mockProvinces'
import { PROVINCES_PROFILE, type ProvinceProfile } from '@/data/recommendation'

const DEFAULT_PROVINCE = '河南'

function defaultIdxFor(arr: { name: string }[]): number {
  const idx = arr.findIndex((p) => p.name === DEFAULT_PROVINCE)
  return idx >= 0 ? idx : 0
}

/** 把 backend 返回的一行(mixed schema:baseline json 或 grain.db)规整成 ProvinceBase。 */
function normalizeRow(row: ProvinceRow): ProvinceBase {
  const name = row.name ?? row.province ?? '未知'
  // grain.db 用 flood_r,baseline json 用 flood;两者保留语义为"洪涝占比 %"
  const flood = row.flood ?? row.flood_r ?? 0
  return {
    name,
    y: row.y ?? 0,
    irr: row.irr ?? 0,
    flood,
    sun: row.sun ?? 0,
    spei: row.spei ?? 0,
    temp: row.temp ?? 0,
    type: row.type ?? '主产区主导型',
  }
}

/** 给规则引擎用的 ProvinceProfile:在 ProvinceBase 基础上补 rank + desc。 */
function buildProfile(arr: ProvinceBase[], descLookup: Map<string, string>): ProvinceProfile[] {
  const ranked = [...arr].sort((a, b) => b.y - a.y)
  return ranked.map((p, i) => ({
    ...p,
    rank: i + 1,
    desc: descLookup.get(p.name)
      ?? `${p.name}:${p.type},年均温 ${p.temp.toFixed(1)}°C,洪涝占比 ${p.flood.toFixed(1)}%。`,
  }))
}

// 把内置 PROVINCES_PROFILE 的 desc 抽出来,真数据没 desc 字段时复用。
const STATIC_DESC = new Map(PROVINCES_PROFILE.map((p) => [p.name, p.desc]))

export const useProvinceStore = defineStore('province', () => {
  // ── 选择状态 ───────────────────────────────────────────────────────────
  const selectedIdx = ref<number>(0)

  // ── 数据状态 ───────────────────────────────────────────────────────────
  /** 31 省当年快照,真后端数据。空数组 = 尚未加载或加载失败。 */
  const provinces = ref<ProvinceBase[]>([])
  /** API 实际返回的原始行,view 需要 grain.db 专有字段(如 ndvi/region)时用。 */
  const rawProvinces = ref<ProvinceRow[]>([])

  const isLoading = ref(false)
  const error = ref<string | null>(null)
  /** 数据来源:'api' = 真后端;'mock' = 加载失败/未加载时骨架;'none' = 初始空 */
  const source = ref<'api' | 'mock' | 'none'>('none')
  /** 首次成功 init 默认省份后置 true,避免用户切了别的省被重置回河南。 */
  const defaultInitialized = ref(false)

  // 给规则引擎(M04)用:每次 provinces 变化重算 profile。
  const profiles = computed<ProvinceProfile[]>(() => {
    const base = provinces.value.length > 0 ? provinces.value : PROVINCES_BASE
    return buildProfile(base, STATIC_DESC)
  })

  /** 当前选中的省份,统一为 ProvinceProfile 形态供 view 直接消费。 */
  const selected = computed<ProvinceProfile>(() => {
    const list = profiles.value
    if (list.length === 0) {
      // 极端兜底:既无 api 又无 mock(理论不可达)
      return {
        name: DEFAULT_PROVINCE,
        y: 0,
        irr: 0,
        flood: 0,
        sun: 0,
        spei: 0,
        temp: 0,
        type: '主产区主导型',
        rank: 1,
        desc: '',
      }
    }
    const idx = Math.max(0, Math.min(selectedIdx.value, list.length - 1))
    return list[idx]
  })

  // ── actions ────────────────────────────────────────────────────────────
  /** 拉一年的 31 省数据。year 缺省走后端默认(最新年或 baseline)。 */
  async function loadProvinces(year?: number): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const rows = await fetchProvinces(year)
      rawProvinces.value = rows
      provinces.value = rows.map(normalizeRow)
      source.value = 'api'
      // 第一次拿到数据时把 selectedIdx 调到默认省份
      if (!defaultInitialized.value) {
        selectedIdx.value = defaultIdxFor(profiles.value)
        defaultInitialized.value = true
      }
    } catch (e: unknown) {
      // 拿不到真数据时,fallback 到 mock baseline,保证 view 不空白崩溃。
      // 此为"骨架"模式,view 应展示 error 状态 + retry。
      provinces.value = [...PROVINCES_BASE]
      rawProvinces.value = []
      source.value = 'mock'
      error.value = e instanceof Error ? e.message : 'network error'
      if (!defaultInitialized.value) {
        selectedIdx.value = defaultIdxFor(profiles.value)
        defaultInitialized.value = true
      }
    } finally {
      isLoading.value = false
    }
  }

  function setIdx(idx: number) {
    const list = profiles.value
    if (idx >= 0 && idx < list.length) selectedIdx.value = idx
  }

  function setByName(name: string) {
    const idx = profiles.value.findIndex((p) => p.name === name)
    if (idx >= 0) selectedIdx.value = idx
  }

  return {
    // state
    selectedIdx,
    provinces,
    rawProvinces,
    isLoading,
    error,
    source,
    // getters
    profiles,
    selected,
    // actions
    loadProvinces,
    setIdx,
    setByName,
  }
})
