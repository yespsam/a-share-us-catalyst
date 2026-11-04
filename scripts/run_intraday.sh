#!/usr/bin/env bash
# Run an intraday anomaly snapshot on A-share cash-session windows.
# Outside those windows the script exits 0 so a 30-minute scheduler can call it all day.
# Set CATDESK_INTRADAY_FORCE=1 to run anyway.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ "${CATDESK_INTRADAY_FORCE:-}" != "1" ]; then
  WD="$(TZ=Asia/Shanghai date +%u)"
  HM="$(TZ=Asia/Shanghai date +%H%M)"
  hm=$((10#$HM))
  if [ "$WD" -gt 5 ]; then
    echo "非交易日，跳过盘中观察。"
    exit 0
  fi
  morning=$([[ "$hm" -ge 935 && "$hm" -le 1130 ]] && echo 1 || echo 0)
  afternoon=$([[ "$hm" -ge 1305 && "$hm" -le 1455 ]] && echo 1 || echo 0)
  if [ "$morning" != 1 ] && [ "$afternoon" != 1 ]; then
    echo "不在连续竞价窗口（09:35-11:30，13:05-14:55），跳过盘中观察。"
    exit 0
  fi
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
. .venv/bin/activate

if ! python -c "import pandas" >/dev/null 2>&1; then
  pip install -r requirements.txt
fi

# Do not auto-send Telegram. A 30-minute job would spam the chat.
PYTHONPATH=src python -m ashare_us_catalyst.cli intraday "$@"
