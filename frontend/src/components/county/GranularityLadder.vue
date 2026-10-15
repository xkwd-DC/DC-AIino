<script setup lang="ts">
/**
 * M07-C 空间粒度递进与口径披露。
 *
 * 存在的理由:县级层的 R² 与省级的 R² 不是同一件事(省级 0.907 测的是省内因子相对重要性,
 * leave-province-out 中位 −16.83 说明跨省空间外推不成立;县级 CLIMG 已剔除规模与省-年常量)。
 * 这一屏把两套口径并排摊开,数字全部来自后端 county_standard 表,前端不写死。
 */
import type { CountyStandard } from '@/api/county'

defineProps<{
  standard: CountyStandard | null
  loading: boolean
  error: string | null
}>()

// 口径诊断里的键 → 展示文案(值本身仍来自后端)
const DIAGNOSIS_LABELS: Record<string, string> = {
  var_share_area: 'log(总产量) 方差中被播种面积解释的份额',
  corr_log_yield_log_area: 'log(总产量) 与 log(播种面积) 的相关系数',
  n_yield_rows: '有单产记录的样本行数',
}
</script>

<template>
  <section class="ladder" aria-labelledby="ladder-title">
    <header class="ladder-head">
      <div>
        <div class="eyebrow">CAVEAT · 口径与迁移体检</div>
        <h3 id="ladder-title">空间粒度递进:从省级到县级,再剥掉规模</h3>
      </div>
      <span v-if="loading" class="badge" role="status" aria-live="polite">加载中…</span>
    </header>

    <p v-if="error" class="ladder-error" role="alert">
      口径表加载失败:{{ error }}。地图仍可用,但请勿在此状态下引用数字。
    </p>

    <template v-else-if="standard">
      <!-- a11y SC 1.4.10 Reflow:窄屏放不下的宽表用可横向滚动的 region 兜住,
           并给 tabindex=0 让键盘用户能滚(内部滚动容器必须可聚焦)。 -->
      <div
        class="table-scroll"
        role="region"
        aria-label="省级与县级两层模型的空间/时间迁移能力对照表，可横向滚动"
        tabindex="0"
      >
        <table class="ladder-table">
          <caption class="sr-only">
            省级与县级两层模型的空间/时间迁移能力对照,以及规模对照实验
          </caption>
          <thead>
            <tr>
              <th scope="col">粒度 / 特征集</th>
              <th scope="col">空间外推(跨单元)</th>
              <th scope="col">时间外推(跨年份)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in standard.ladder" :key="row.level">
              <th scope="row">
                <span class="lv">{{ row.level }}</span>
                <span class="scope">{{ row.scope }}</span>
              </th>
              <td class="mono">{{ row.lco_r2 }}</td>
              <td class="mono">{{ row.time_r2 }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <ul v-if="standard.ladder.some((r) => r.reading)" class="readings">
        <li v-for="row in standard.ladder.filter((r) => r.reading)" :key="row.level">
          <b>{{ row.level }}</b>:{{ row.reading }}
        </li>
      </ul>

      <div class="evidence-grid">
        <div class="evidence">
          <h4>阴性对照(permutation)</h4>
          <p class="hint">
            把特征逐列打乱重跑 30 次。若真实 R² 与打乱后差不多,说明 R² 是结构性假象。
          </p>
          <ul class="null-list">
            <li v-for="n in standard.nulls" :key="n.config">
              <span class="cfg mono">{{ n.config }}({{ n.n_feat }} 维)</span>
              <span class="mono">真实 {{ n.true_mean }} vs null {{ n.null_mean }}</span>
              <span class="mono dim">超额 {{ n.excess }} · 真实>null 占比 {{ n.frac_true_gt_null }}</span>
            </li>
          </ul>
        </div>
        <div class="evidence">
          <h4>增益显著性(bootstrap 跨县重采样)</h4>
          <dl v-if="standard.bootstrap.delta_point">
            <dt>CLIM3 → CLIMG 增益</dt>
            <dd class="mono">
              Δ = {{ standard.bootstrap.delta_point }}
              (95%CI {{ standard.bootstrap.ci_lo }} ~ {{ standard.bootstrap.ci_hi }})
            </dd>
            <dt>P(Δ ≤ 0)</dt>
            <dd class="mono">{{ standard.bootstrap.p_delta_le_0 }}</dd>
            <dt>重采样次数 / 共同样本</dt>
            <dd class="mono">{{ standard.bootstrap.n_boot }} × / {{ standard.bootstrap.n_common }} 行</dd>
          </dl>
          <p v-else class="muted">未登记</p>
        </div>
        <div class="evidence">
          <h4>规模口径诊断</h4>
          <dl v-if="Object.keys(standard.scale_diagnosis).length">
            <template v-for="(v, k) in standard.scale_diagnosis" :key="k">
              <dt>{{ DIAGNOSIS_LABELS[k] ?? k }}</dt>
              <dd class="mono">{{ v }}</dd>
            </template>
          </dl>
          <p v-else class="muted">未登记</p>
          <p v-if="standard.scale_note" class="hint">{{ standard.scale_note }}</p>
        </div>
      </div>

      <p class="note">{{ standard.note }}</p>
      <p class="provenance">
        数字出处:{{ standard.ladder[0]?.source }} 等 ·
        复核自 <span class="mono">reports/v6_12_*.csv</span>、<span class="mono">reports/v6_13_*.csv</span>
      </p>
    </template>
  </section>
</template>

<style scoped>
.ladder {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--sp-5);
}
.ladder-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
}
.eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.2px;
  color: var(--text-3);
  text-transform: uppercase;
}
h3 {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 600;
  margin-top: var(--sp-1);
}
h4 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: var(--sp-2);
}
.badge {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
}
.ladder-error { color: var(--amber-bright); font-size: 12px; }

.table-scroll {
  overflow-x: auto;
  border-radius: var(--r-sm);
}
.table-scroll:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}
.ladder-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.ladder-table th,
.ladder-table td {
  text-align: left;
  padding: var(--sp-3);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.ladder-table thead th {
  font-size: 11px;
  color: var(--text-3);
  font-weight: 500;
  white-space: nowrap;
}
.ladder-table tbody th { font-weight: 500; }
.ladder-table .mono {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--green-bright);
  white-space: nowrap;
}
.lv { display: block; color: var(--text); }
.scope { display: block; color: var(--text-3); font-weight: 400; font-size: 11px; margin-top: 2px; }

.readings {
  margin-top: var(--sp-3);
  padding-left: var(--sp-5);
  font-size: 12px;
  color: var(--text-2);
}
.readings li { margin-bottom: var(--sp-1); }
.readings b { color: var(--text); font-weight: 600; }

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--sp-4);
  margin-top: var(--sp-5);
}
.evidence {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: var(--sp-4);
}
.evidence dl { font-size: 12px; }
.evidence dt { color: var(--text-3); font-size: 11px; margin-top: var(--sp-2); }
.evidence dt:first-child { margin-top: 0; }
.evidence dd { color: var(--text-2); }
.evidence dd.mono { font-family: var(--font-mono); font-size: 11.5px; color: var(--green-bright); }
.muted { color: var(--text-3); font-size: 12px; }
.hint { font-size: 11px; color: var(--text-3); margin-bottom: var(--sp-3); }
.null-list { list-style: none; font-size: 11.5px; }
.null-list li {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: var(--sp-2) 0;
  border-top: 1px solid var(--border);
}
.null-list li:first-child { border-top: none; }
.null-list .cfg { color: var(--text); }
.null-list .mono { font-family: var(--font-mono); font-size: 11px; color: var(--green-bright); }
.null-list .dim { color: var(--text-3); }

.note {
  margin-top: var(--sp-5);
  font-size: 12px;
  color: var(--text-2);
  border-left: 2px solid var(--green-deep);
  padding-left: var(--sp-3);
}
.provenance {
  margin-top: var(--sp-3);
  font-size: 11px;
  color: var(--text-3);
}
.provenance .mono { font-family: var(--font-mono); }
</style>
