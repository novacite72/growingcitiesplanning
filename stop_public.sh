#!/usr/bin/env bash
# 외부 공개 서비스 중지
pkill -f "gunicorn -w" 2>/dev/null && echo "앱 서버 중지" || echo "앱 서버 없음"
pkill -f "cloudflared tunnel" 2>/dev/null && echo "터널 중지" || echo "터널 없음"
