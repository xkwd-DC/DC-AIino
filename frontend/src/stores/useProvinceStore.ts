/**
 * HIGH#8 — 统一省份选择状态。
 *
 * ScenarioSim 与 ResiliencePath 之前各自 `selectedIdx = ref(findIndex('河南'))`，
 * 同一会话内两个 view 的选择不同步、PROVINCES_BASE / ALL_DATA 数据源排序口径有歧。
 * 抽到 Pinia 后两 view 共享同一 source-of-truth，未来切真后端只改本 store。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { PROVINCES_PROFILE, type ProvinceProfile } from '@/data/recommendation'

const DEFAULT_PROVINCE = '河南'

function findDefaultIdx(): number {
  const idx = PROVINCES_PROFILE.findIndex((p) => p.name === DEFAULT_PROVINCE)
  return idx >= 0 ? idx : 0
}

export const useProvinceStore = defineStore('province', () => {
  const selectedIdx = ref<number>(findDefaultIdx())

  const selected = computed<ProvinceProfile>(() => PROVINCES_PROFILE[selectedIdx.value])

  function setIdx(idx: number) {
    if (idx >= 0 && idx < PROVINCES_PROFILE.length) {
      selectedIdx.value = idx
    }
  }

  function setByName(name: string) {
    const idx = PROVINCES_PROFILE.findIndex((p) => p.name === name)
    if (idx >= 0) selectedIdx.value = idx
  }

  return { selectedIdx, selected, setIdx, setByName }
})
