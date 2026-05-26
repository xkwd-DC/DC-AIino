#!/usr/bin/env bash
# scripts/retrain_all.sh — 一键重训 3 模型（XGB / LSTM / Att-LSTM）× 10 种子
#
# 用途：国家级大创结题 / 论文 reviewer 验证 / 中期检查的复现入口。
# 同步参考：docs/15_训练复现指南.md
#
# 跑法（默认 10 种子 0..9）：
#   bash scripts/retrain_all.sh
#
# 自定义种子集（逗号分隔）：
#   SEEDS=0,1,2 bash scripts/retrain_all.sh
#
# 跳过个别模型（例：仅跑 XGB + LSTM）：
#   SKIP_ATT_LSTM=1 bash scripts/retrain_all.sh
#
# 关键约束（务必遵守）：
#   1) 当前训练脚本（train_*.py）顶部硬编码 SEEDS=list(range(10))；本 wrapper
#      不会重写脚本，只把 SEEDS 写到 env 供未来 v2 接受。如需精确控制种子，
#      请在脚本顶部直接改 `SEEDS = [...]` 列表（属于源码 patch，单独 commit）。
#   2) 数据路径硬编码 `data/interim/paper_panel_v3.parquet`，必须从 git root 跑。
#   3) 训练 artifact 落到 `backend/models/`（覆盖已有 8 个文件）。
#   4) 本脚本只是 wrapper，不改算法逻辑（守 §4 v6 叙事 + 严格约束）。

set -euo pipefail

# ─── 0. 切到 git root ──────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# ─── 1. 环境校验 ──────────────────────────────────────────────────────────
PY_BIN="${PY_BIN:-/tmp/dc-infer/bin/python}"
if [[ ! -x "${PY_BIN}" ]]; then
    # 兜底：找 python3.10
    if command -v python3.10 >/dev/null 2>&1; then
        PY_BIN="python3.10"
    else
        echo "[retrain_all] ERROR: 未找到 python3.10。" >&2
        echo "[retrain_all] 请先按 docs/15_训练复现指南.md §1 创建 /tmp/dc-infer venv。" >&2
        exit 1
    fi
fi

echo "[retrain_all] PY_BIN=${PY_BIN}"
"${PY_BIN}" --version
echo "[retrain_all] repo_root=${REPO_ROOT}"
echo "[retrain_all] 时间戳：$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ─── 2. 数据快照 hash 验证 ────────────────────────────────────────────────
DATA_PATH="data/interim/paper_panel_v3.parquet"
EXPECTED_SHA256="5f0a7561e9af528f8b4a2ab540dec266b00c21e713d41e3f57064058f41d70a4"

if [[ ! -f "${DATA_PATH}" ]]; then
    echo "[retrain_all] ERROR: ${DATA_PATH} 不存在。请先拉取石灵子 PR #7 落地的数据。" >&2
    exit 2
fi

ACTUAL_SHA256="$(sha256sum "${DATA_PATH}" | awk '{print $1}')"
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
    echo "[retrain_all] ⚠️  WARN: 数据 SHA-256 不匹配 model card 记录的版本：" >&2
    echo "[retrain_all]   expected: ${EXPECTED_SHA256}" >&2
    echo "[retrain_all]   actual:   ${ACTUAL_SHA256}" >&2
    echo "[retrain_all] 继续重训但请记录差异（可能 v4 数据已落地）。" >&2
else
    echo "[retrain_all] ✓ 数据 SHA-256 匹配 v3 快照（${EXPECTED_SHA256:0:12}...）"
fi

# ─── 3. 输出 / 日志目录 ────────────────────────────────────────────────────
mkdir -p reports
TS="$(date -u '+%Y%m%dT%H%M%SZ')"
LOG_DIR="reports/retrain_${TS}"
mkdir -p "${LOG_DIR}"
SUMMARY_CSV="reports/seeds_results.csv"

echo "[retrain_all] 日志目录：${LOG_DIR}"
echo "[retrain_all] 汇总 CSV：${SUMMARY_CSV}"

# ─── 4. 训练 3 模型 ───────────────────────────────────────────────────────
SKIP_XGB="${SKIP_XGB:-0}"
SKIP_LSTM="${SKIP_LSTM:-0}"
SKIP_ATT_LSTM="${SKIP_ATT_LSTM:-0}"
# SEEDS env var：当前 v1 wrapper 仅 echo，不传入脚本（v2 训练脚本接受 sys.argv 后启用）
echo "[retrain_all] SEEDS=${SEEDS:-0,1,2,3,4,5,6,7,8,9}（v1 仅记录，训练脚本硬编 0..9）"

run_one () {
    local name="$1"
    local script="$2"
    local logfile="${LOG_DIR}/${name}.log"

    echo
    echo "================================================================"
    echo "[retrain_all] ▶ 训练 ${name}（${script}）"
    echo "[retrain_all]   日志：${logfile}"
    echo "================================================================"

    local start_ts
    start_ts="$(date -u '+%s')"

    if "${PY_BIN}" "${script}" 2>&1 | tee "${logfile}"; then
        local end_ts
        end_ts="$(date -u '+%s')"
        echo "[retrain_all] ✓ ${name} 完成（耗时 $((end_ts - start_ts))s）"
    else
        echo "[retrain_all] ✗ ${name} 失败，看日志：${logfile}" >&2
        return 1
    fi
}

if [[ "${SKIP_XGB}" != "1" ]]; then
    run_one "xgb"      "train_xgb_baseline.py"
fi

if [[ "${SKIP_LSTM}" != "1" ]]; then
    run_one "lstm"     "train_lstm_baseline.py"
fi

if [[ "${SKIP_ATT_LSTM}" != "1" ]]; then
    run_one "att_lstm" "train_att_lstm_baseline.py"
fi

# ─── 5. 汇总 seeds_results.csv（从 backend/models/*_seeds_results.json） ──
echo
echo "================================================================"
echo "[retrain_all] ▶ 汇总 3 模型 × 10 种子结果 → ${SUMMARY_CSV}"
echo "================================================================"

"${PY_BIN}" - <<'PYAGG'
import json
import csv
import sys
from pathlib import Path

MODELS = Path("backend/models")
OUT = Path("reports/seeds_results.csv")

rows = []
sources = {
    "xgb": "xgb_seeds_results.json",
    "lstm": "lstm_seeds_results.json",
    "att_lstm": "att_lstm_seeds_results.json",
}

for model_name, fname in sources.items():
    p = MODELS / fname
    if not p.exists():
        print(f"[retrain_all][agg] skip {model_name}: {p} 未生成（可能 SKIP_*=1）")
        continue
    d = json.loads(p.read_text())
    for s in d["per_seed"]:
        rows.append({
            "model":  model_name,
            "seed":   s["seed"],
            "tr_r2":  round(s["tr_r2"], 6),
            "te_r2":  round(s["te_r2"], 6),
            "tr_rmse_kg_per_ha": round(s["tr_rmse_kg_per_ha"], 3),
            "te_rmse_kg_per_ha": round(s["te_rmse_kg_per_ha"], 3),
            "epochs_run": s.get("epochs_run", ""),
        })

if not rows:
    print("[retrain_all][agg] no seeds results produced — nothing to write", file=sys.stderr)
    sys.exit(0)

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print(f"[retrain_all][agg] ✓ wrote {len(rows)} rows → {OUT}")
PYAGG

# ─── 6. 推理 sanity（河南 2022） ──────────────────────────────────────────
echo
echo "================================================================"
echo "[retrain_all] ▶ 推理 sanity check（河南 2022 → 真值 4615 kg/ha）"
echo "================================================================"

if PYTHONPATH=backend "${PY_BIN}" -m services.inference 2>&1 | tee "${LOG_DIR}/inference_sanity.log"; then
    echo "[retrain_all] ✓ sanity PASS（三模型容差均通过）"
else
    echo "[retrain_all] ⚠️  sanity FAIL — 看 ${LOG_DIR}/inference_sanity.log；可能 keras 版本兼容/路径错。" >&2
    echo "[retrain_all]    若是单次种子偏移可重跑；持续失败查 docs/15_训练复现指南.md §7。" >&2
fi

# ─── 7. 收尾 ───────────────────────────────────────────────────────────────
echo
echo "================================================================"
echo "[retrain_all] ✅ 全部完成。"
echo "[retrain_all]   日志：${LOG_DIR}/"
echo "[retrain_all]   汇总：${SUMMARY_CSV}"
echo "[retrain_all]   模型 artifact：backend/models/"
echo "================================================================"
