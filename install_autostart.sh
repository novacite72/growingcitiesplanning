#!/usr/bin/env bash
# 부팅 시 자동 실행 등록 — gunicorn(앱)과 cloudflared(고정 터널)를 각각 launchd 잡으로 등록.
# 두 잡 모두 포그라운드로 동작하므로 KeepAlive로 죽으면 자동 재시작됩니다.
set -e
cd "$(dirname "$0")"
APPDIR="$(pwd)"
GUNICORN="$(command -v gunicorn || echo "$HOME/anaconda3/bin/gunicorn")"
CF="$APPDIR/bin/cloudflared"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA"

echo "▶ 기존 수동 프로세스 정리…"
pkill -f "gunicorn -w" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1

# 1) 앱 서버 (gunicorn, PUBLIC=1)
cat > "$LA/re.si.seoulbook.app.plist" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>re.si.seoulbook.app</string>
  <key>ProgramArguments</key>
  <array>
    <string>$GUNICORN</string><string>-w</string><string>1</string>
    <string>--threads</string><string>8</string>
    <string>-b</string><string>0.0.0.0:8000</string><string>app:app</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PUBLIC</key><string>1</string><key>PORT</key><string>8000</string>
  </dict>
  <key>WorkingDirectory</key><string>$APPDIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/seoulbook.app.log</string>
  <key>StandardErrorPath</key><string>/tmp/seoulbook.app.log</string>
</dict></plist>
XML

# 2) 고정 터널 (cloudflared named tunnel)
cat > "$LA/re.si.seoulbook.tunnel.plist" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>re.si.seoulbook.tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>$CF</string><string>tunnel</string>
    <string>--config</string><string>$APPDIR/cloudflared.yml</string><string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$APPDIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/seoulbook.tunnel.log</string>
  <key>StandardErrorPath</key><string>/tmp/seoulbook.tunnel.log</string>
</dict></plist>
XML

echo "▶ launchd 등록…"
launchctl unload "$LA/re.si.seoulbook.app.plist" 2>/dev/null || true
launchctl unload "$LA/re.si.seoulbook.tunnel.plist" 2>/dev/null || true
launchctl load "$LA/re.si.seoulbook.app.plist"
launchctl load "$LA/re.si.seoulbook.tunnel.plist"
echo "✅ 자동시작 등록 완료 (재부팅 시 자동 실행)"
echo "   해제:  ./uninstall_autostart.sh"
