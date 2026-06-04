#!/usr/bin/env bash
# scripts/data/v4_fetch.sh — v4 数据扩展拉取编排器
#
# 用途：6/1 W23 启动后一键全量下载 v4 三方向所需数据。
# 同步参考：docs/16_v4_plan.md §1 / scripts/data/README.md
#
# 三阶段（与 v4 plan §1 对齐）：
#   8a 致灾因子真实化     ：水旱灾害公报 PDF + 农业灾害分布 + NASA POWER daily (prec_50mm_days)
#   8b MODIS 耕地像元加权 ：复用 CLCD_2022 一年（已在库），无需额外下载，本脚本只做 sanity check
#   8c 多年 CLCD 替换单年 ：CLCD 2011-2023 全 13 年（约 10 GB，Zenodo）
#
# 跑法：
#   bash scripts/data/v4_fetch.sh                       # 默认 dry-run，全 phase，只打印将做什么
#   bash scripts/data/v4_fetch.sh --execute             # 实跑
#   bash scripts/data/v4_fetch.sh --phase 8c --execute  # 单跑 8c（CLCD）
#   PHASE=8a bash scripts/data/v4_fetch.sh --execute    # 同上，env var 写法
#
# 环境约束：
#   1) 必须从 git root 跑（脚本自己会 cd 过去）
#   2) 用 .venv-data venv（与 backend 隔离，遵守 scripts/data/README.md §环境）
#   3) 凭证写 .env（已 gitignored，模板见 .env.example）
#   4) 长尾审批账号（CMA 气象数据中心 1-2 周）见 docs/coord/2026-05-27_v4_account_checklist.md

set -euo pipefail

# ─── 0. 切到 git root ──────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

# ─── 1. 参数解析 ──────────────────────────────────────────────────────────
PHASE="${PHASE:-all}"
MODE="dry-run"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --phase) PHASE="$2"; shift 2 ;;
        --execute) MODE="execute"; shift ;;
        --dry-run) MODE="dry-run"; shift ;;
        -h|--help)
            grep -E '^#' "$0" | head -30
            exit 0
            ;;
        *) echo "未知参数 $1" >&2; exit 2 ;;
    esac
done

case "${PHASE}" in
    all|8a|8b|8c) ;;
    *) echo "[v4_fetch] ERROR: --phase 必须是 all/8a/8b/8c，收到 ${PHASE}" >&2; exit 2 ;;
esac

# ─── 2. 环境校验 ──────────────────────────────────────────────────────────
PY_BIN="${PY_BIN:-${REPO_ROOT}/.venv-data/bin/python}"
if [[ ! -x "${PY_BIN}" ]]; then
    echo "[v4_fetch] ERROR: 未找到 .venv-data Python (${PY_BIN})" >&2
    echo "[v4_fetch] 请先按 scripts/data/README.md §环境 跑：" >&2
    echo "  uv venv --python 3.11 .venv-data" >&2
    echo "  uv pip install --python .venv-data/bin/python -r scripts/data/requirements-pipeline.txt" >&2
    exit 1
fi

# 加载 .env（如果存在）
if [[ -f "${REPO_ROOT}/.env" ]]; then
    set -a; . "${REPO_ROOT}/.env"; set +a
fi

# ─── 3. 日志 ─────────────────────────────────────────────────────────────
LOG_DIR="${REPO_ROOT}/data/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/v4_fetch_$(date -u '+%Y-%m-%dT%H%M%SZ').log"

log()  { echo "[v4_fetch] $*" | tee -a "${LOG_FILE}"; }
step() { log ""; log "=== $* ==="; }

log "REPO_ROOT=${REPO_ROOT}"
log "PY_BIN=${PY_BIN}"
log "PHASE=${PHASE}"
log "MODE=${MODE}"
log "LOG_FILE=${LOG_FILE}"
log "开始时间 $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

if [[ "${MODE}" == "dry-run" ]]; then
    log ""
    log "*** DRY-RUN 模式 — 只打印将做什么，不实际下载 ***"
    log "*** 实跑请加 --execute ***"
fi

# ─── 4. Phase 8a · 致灾因子真实化 ─────────────────────────────────────────
run_8a() {
    step "Phase 8a: 致灾因子真实化"

    log "--- 8a.1 水旱灾害公报 (2011-2023, 13 份) ---"
    log "来源 水利部官方  http://www.mwr.gov.cn/sj/tjgb/szhzhgb/"
    log "形式 PDF 扫描件（近年含 Excel 附表），需 OCR + 双人校对"
    log "状态 [手动] 本周内 (5/27-5/31) 由石灵子手工下载到 data/raw/disaster_bulletin/"
    log "脚本 scripts/data/09_ocr_disaster_bulletin.py （待写，W23 起）"
    log ""

    log "--- 8a.2 中国农业灾害分布数据集 ---"
    log "首选 国家青藏高原科学数据中心  https://data.tpdc.ac.cn/  (需账号 + 用途说明)"
    log "备选 中科院资环所             https://www.resdc.cn/    (账号申请审批 ~3 工作日)"
    log "形式 csv / Excel"
    log "状态 [手动] 账号审批通过后由石灵子下载到 data/raw/agri_disaster/"
    log "依赖 docs/coord/2026-05-27_v4_account_checklist.md §1-§2 账号通过"
    log ""

    log "--- 8a.3 NASA POWER daily → prec_50mm_days ---"
    log "来源 NASA POWER REST API （已有 00b_fetch_nasa_power.py 月度版）"
    log "形式 daily 降水 → 衍生年内日降水 ≥ 50mm 日数"
    log "脚本 scripts/data/00b_fetch_nasa_power.py --daily （需小改 / 加 --daily 参数）"
    if [[ "${MODE}" == "execute" ]]; then
        log "[TODO] 待 00b 加 --daily 参数后执行"
    else
        log "[DRY-RUN] 跳过实跑"
    fi
}

# ─── 5. Phase 8b · MODIS 耕地像元加权 ────────────────────────────────────
run_8b() {
    step "Phase 8b: MODIS 耕地像元加权 sanity"

    log "8b 无新增下载需求 — CLCD_2022 已在 data/raw/gis_cropland/"
    log "主战场为脚本开发：scripts/data/05b_modis_cropland_weighted.py (W26 起，见 v4 plan §1.2)"
    log ""

    CLCD_2022="${REPO_ROOT}/data/raw/gis_cropland/CLCD_v01_2022_albert.tif"
    if [[ -f "${CLCD_2022}" ]]; then
        SIZE=$(stat -c %s "${CLCD_2022}")
        log "[OK] CLCD 2022 在库  ${SIZE} B"
    else
        log "[MISS] CLCD 2022 不在库 — 需先跑 01_download_cropland.py --year 2022"
    fi

    MODIS_DIR="${REPO_ROOT}/data/raw/modis_ndvi"
    if [[ -d "${MODIS_DIR}" ]]; then
        COUNT=$(find "${MODIS_DIR}" -type f 2>/dev/null | wc -l)
        log "[OK] MODIS NDVI 目录  ${COUNT} 个文件"
    else
        log "[MISS] MODIS NDVI 目录不存在 — M1 任务未完成？"
    fi
}

# ─── 6. Phase 8c · 多年 CLCD 2011-2023 ────────────────────────────────────
run_8c() {
    step "Phase 8c: CLCD 2011-2023 全 13 年下载"

    log "来源 Zenodo record 12779975 (CLCD v01)"
    log "总量 约 10 GB （13 年 × ~770 MB / 年）"
    log "脚本 scripts/data/01_download_cropland.py --years 2011-2023"
    log "断点续传 ✓ 已支持 (.partial 文件)"
    log "盘空间审计："
    FREE_GB=$(df -BG "${REPO_ROOT}/data" 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}')
    if [[ -n "${FREE_GB:-}" ]]; then
        log "  可用 ${FREE_GB} GB （需要 ≥ 12 GB 缓冲）"
        if [[ "${FREE_GB}" -lt 12 ]]; then
            log "  [WARN] 盘空间紧张 — 考虑 README §储存策略 方案 A (COG 流式) 或方案 B (外置盘)"
        fi
    fi
    log ""

    if [[ "${MODE}" == "execute" ]]; then
        log "[RUN] ${PY_BIN} scripts/data/01_download_cropland.py --years 2011-2023"
        "${PY_BIN}" scripts/data/01_download_cropland.py --years 2011-2023 2>&1 | tee -a "${LOG_FILE}"
    else
        log "[DRY-RUN] ${PY_BIN} scripts/data/01_download_cropland.py --years 2011-2023 --dry-run"
        "${PY_BIN}" scripts/data/01_download_cropland.py --years 2011-2023 --dry-run 2>&1 | tee -a "${LOG_FILE}"
    fi
}

# ─── 7. 主流程 ──────────────────────────────────────────────────────────
case "${PHASE}" in
    all) run_8a; run_8b; run_8c ;;
    8a)  run_8a ;;
    8b)  run_8b ;;
    8c)  run_8c ;;
esac

step "完成"
log "结束时间 $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
log "日志    ${LOG_FILE}"
