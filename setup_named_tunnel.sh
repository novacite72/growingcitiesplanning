#!/usr/bin/env bash
# 고정 주소(named tunnel) 설정 — 1회만 실행하면 영구 URL이 만들어집니다.
# 전제: ① Cloudflare 계정, ② Cloudflare에 등록된 도메인(예: example.com)
# 사용: ./setup_named_tunnel.sh book.example.com
set -e
cd "$(dirname "$0")"
CF="./bin/cloudflared"
HOST="${1:?사용법: ./setup_named_tunnel.sh <공개에 쓸 호스트명, 예: book.si.re.kr>}"
NAME="seoul-book"

echo "▶ 1/4  Cloudflare 로그인 (브라우저가 열립니다 → 도메인 선택 후 승인)"
"$CF" tunnel login

echo "▶ 2/4  터널 생성: $NAME"
"$CF" tunnel create "$NAME" 2>/dev/null || echo "   (이미 존재 — 계속)"
UUID="$("$CF" tunnel list | awk -v n="$NAME" '$2==n{print $1}')"
echo "   tunnel UUID = $UUID"

echo "▶ 3/4  DNS 연결: $HOST → 터널"
"$CF" tunnel route dns "$NAME" "$HOST"

echo "▶ 4/4  설정 파일 생성: ./cloudflared.yml"
cat > cloudflared.yml <<YML
tunnel: $UUID
credentials-file: $HOME/.cloudflared/$UUID.json
ingress:
  - hostname: $HOST
    service: http://localhost:8000
  - service: http_status:404
YML

echo
echo "============================================================"
echo "  ✅ 고정 주소 설정 완료:  https://$HOST"
echo "  실행:  ./serve_named.sh    (gunicorn + 고정 터널)"
echo "  자동시작 등록:  ./install_autostart.sh"
echo "============================================================"
