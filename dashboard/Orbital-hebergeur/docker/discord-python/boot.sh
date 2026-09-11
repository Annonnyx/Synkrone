#!/bin/sh
set -e
cd /app
echo "[synkrone] booting python discord runtime"
TOKEN="${DISCORD_TOKEN:-$BOT_TOKEN}"
if [ -z "$TOKEN" ]; then
  echo "[fatal] BOT_TOKEN is not set - the panel must inject it" >&2
  exit 0
fi
export DISCORD_TOKEN="$TOKEN"
export BOT_TOKEN="$TOKEN"
if [ -f requirements.txt ]; then
  echo "[synkrone] installing python dependencies"
  python -m pip install --user --no-cache-dir -r requirements.txt
fi
echo "[synkrone] starting bot"
exec python -u main.py
