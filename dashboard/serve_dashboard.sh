#!/usr/bin/env bash
# Serve the DC project cockpit behind HTTP Basic Auth via a cloudflared quick tunnel.
# Launches both as fully-detached daemons (setsid) so they survive the agent task lifecycle.
# Note: trycloudflare quick tunnels have NO uptime guarantee and the URL changes on each start.
set -uo pipefail

DIR=/home/darcy/DC/dashboard
PORT=8088
CFLOG=/tmp/dash_cf.log
HTTPLOG=/tmp/dash_http.log

# clean any previous instances
pkill -f "auth_server.py ${PORT}" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" 2>/dev/null || true
: > "$CFLOG"; : > "$HTTPLOG"

cd "$DIR" || exit 1
if [ ! -f .dash_pass ]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(12))" > .dash_pass
  chmod 600 .dash_pass
fi

setsid nohup python3 auth_server.py "$PORT" >"$HTTPLOG" 2>&1 < /dev/null &
setsid nohup cloudflared tunnel --url "http://127.0.0.1:${PORT}" >"$CFLOG" 2>&1 < /dev/null &

# block until the tunnel URL appears (no sleep), max 60s
URL=$(timeout 60 grep -m1 -oE 'https://[a-z0-9-]+\.trycloudflare\.com' <(tail -f "$CFLOG"))
if [ -n "${URL:-}" ]; then
  echo "URL:  $URL"
  echo "user: darcy"
  echo "pass: $(cat .dash_pass)"
else
  echo "URL not ready; cf.log tail:"; tail -8 "$CFLOG"; exit 1
fi
