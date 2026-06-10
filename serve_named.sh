#!/usr/bin/env bash
# 고정 주소(named tunnel)로 서비스 실행 — cloudflared.yml 필요(setup_named_tunnel.sh로 생성)
set -e
cd "$(dirname "$0")"
GUNICORN="$(command -v gunicorn || echo "$HOME/anaconda3/bin/gunicorn")"
pkill -f "gunicorn -w" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1
PUBLIC=1 PORT=8000 nohup "$GUNICORN" -w 1 --threads 8 -b 0.0.0.0:8000 app:app > /tmp/gunicorn.log 2>&1 &
sleep 2
nohup ./bin/cloudflared tunnel --config ./cloudflared.yml run > /tmp/cf.log 2>&1 &
echo "▶ 고정 주소로 실행됨. cloudflared.yml의 hostname으로 접속하세요."
