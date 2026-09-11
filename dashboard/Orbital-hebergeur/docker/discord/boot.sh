#!/bin/sh
set -e
cd /app
if [ -z "$BOT_TOKEN" ]; then
  echo "[fatal] BOT_TOKEN is not set - the panel must inject it" >&2
  exit 0
fi
if [ ! -d node_modules ] || [ package.json -nt node_modules ]; then
  echo "[orbital] installing dependencies"
  npm install --omit=dev --no-audit --no-fund
fi
echo "[orbital] starting Discord bot"
exec node index.js
