#!/usr/bin/env bash
LA="$HOME/Library/LaunchAgents"
launchctl unload "$LA/re.si.seoulbook.app.plist" 2>/dev/null && echo "앱 잡 해제"
launchctl unload "$LA/re.si.seoulbook.tunnel.plist" 2>/dev/null && echo "터널 잡 해제"
rm -f "$LA/re.si.seoulbook.app.plist" "$LA/re.si.seoulbook.tunnel.plist"
echo "자동시작 등록 제거 완료"
