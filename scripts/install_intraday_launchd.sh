#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.qohfq.ashare-us-catalyst.intraday"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT_DIR/logs"
chmod +x "$ROOT_DIR/scripts/run_intraday.sh"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT_DIR/scripts/run_intraday.sh</string>
  </array>
  <key>StartInterval</key>
  <integer>1800</integer>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>StandardOutPath</key>
  <string>$ROOT_DIR/logs/intraday-launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT_DIR/logs/intraday-launchd.err.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
echo "已安装：${LABEL}，每 30 分钟唤起一次。"
echo "scripts/run_intraday.sh 会在非交易时段直接退出，实际只在周一至周五 09:35-11:30 和 13:05-14:55 生成报告。"
echo "配置文件：${PLIST}"
