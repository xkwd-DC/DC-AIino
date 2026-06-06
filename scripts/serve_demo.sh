#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# 稷韧云图 · 一键拉起完整答辩演示栈(单隧道架构)
# ───────────────────────────────────────────────────────────────────────────
# 一条 cloudflared 隧道同时托管【系统】与【答辩 Slidev】:
#     <隧道URL>/overview        → 完整系统
#     <隧道URL>/deck/index.html → 8 分钟答辩 deck(内嵌系统 iframe,同源)
#
# 重启服务器后,跑这一条即可全栈复活:
#     bash /home/darcy/DC/DC/scripts/serve_demo.sh
#
# 关键约定:后端 venv 在 ext4(backend/.venv-rt,持久);
#          不要把包装到 /tmp(那是 4G 内存盘,重启即清 —— 之前"重启就崩"的根因)。
# ═══════════════════════════════════════════════════════════════════════════
set -u
ROOT="/home/darcy/DC/DC"
VENV="$ROOT/backend/.venv-rt"
export TMPDIR="$ROOT/.piptmp"
LOG="$ROOT/.demo-logs"; mkdir -p "$TMPDIR" "$LOG"

cfurl()   { grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$1" 2>/dev/null | head -1; }
waitport(){ for _ in $(seq 1 "$2"); do curl -sf "http://localhost:$1/" >/dev/null 2>&1 && return 0; sleep 1; done; return 1; }
waiturl() { for _ in $(seq 1 40); do [ -n "$(cfurl "$1")" ] && return 0; sleep 1; done; return 1; }

echo "[1/6] 停止旧进程 ..."
pkill -9 -f "gunicorn.*app:app"  2>/dev/null || true
pkill -9 -f "vite"               2>/dev/null || true
pkill -9 -f "cloudflared tunnel" 2>/dev/null || true
sleep 2

echo "[2/6] 后端 gunicorn :5000 (无 --preload,避开 TF fork 死锁) ..."
nohup "$VENV/bin/gunicorn" --chdir "$ROOT/backend" -w 1 --threads 4 -t 180 \
      -b 127.0.0.1:5000 app:app > "$LOG/gunicorn.log" 2>&1 &

echo "[3/6] 前端 vite :5173 ..."
( cd "$ROOT/frontend" && nohup npm run dev > "$LOG/vite.log" 2>&1 & )
waitport 5173 45 && echo "    ✓ vite ready" || echo "    ⚠ vite 未就绪(查 $LOG/vite.log)"

echo "[4/6] 构建答辩 deck → frontend/public/deck (base /deck/, 同源 iframe) ..."
( cd "$ROOT/slidev" && node_modules/.bin/slidev build slides.md \
    --out "$ROOT/frontend/public/deck" --base /deck/ > "$LOG/deck-build.log" 2>&1 ) \
  && echo "    ✓ deck 已构建" || echo "    ⚠ deck 构建失败(查 $LOG/deck-build.log)"

echo "[5/6] 健康检查 ..."
curl -sf http://localhost:5000/api/health >/dev/null 2>&1 && echo "    ✓ 后端 /api/health" || echo "    ⚠ 后端未就绪"

echo "[6/6] cloudflared 隧道 (→5173) ..."
nohup cloudflared tunnel --url http://localhost:5173 > "$LOG/cf.log" 2>&1 &
waiturl "$LOG/cf.log"; SYS="$(cfurl "$LOG/cf.log")"

echo
echo "════════════════════════════════════════════════════════════════"
if [ -n "${SYS:-}" ]; then
  echo "  ✅ 完整系统:    ${SYS}/overview"
  echo "  ✅ 答辩 Slidev:  ${SYS}/deck/index.html"
else
  echo "  ⚠ 隧道未取到 URL(trycloudflare 可能限流) —— 稍等几分钟重跑本脚本;"
  echo "     或本地直连演示:"
fi
echo "  本地直连:        系统 http://localhost:5173    ·    deck http://localhost:5173/deck/index.html"
echo "  演讲者模式(带备注+计时):  在 deck URL 后加 /presenter,或本地 npm run dev 后访问 :3030/presenter"
echo "  日志目录:        $LOG"
echo "════════════════════════════════════════════════════════════════"
