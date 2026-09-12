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
# Keep site-packages on the mounted volume so a container recreate still has discord.py.
export PYTHONPATH="/app/.orbital/py:${PYTHONPATH:-}"
export PATH="/app/.orbital/py/bin:/root/.local/bin:${PATH}"
if [ -f requirements.txt ]; then
  HASH=$(sha256sum requirements.txt | awk '{print $1}')
  mkdir -p /app/.orbital/py
  if [ -f /app/.orbital/reqs.ok ] && [ "$(cat /app/.orbital/reqs.ok)" = "v2:$HASH" ] && python -c "import discord" >/dev/null 2>&1; then
    echo "[synkrone] python dependencies already installed"
  else
    echo "[synkrone] installing python dependencies"
    python -m pip install --target /app/.orbital/py --no-cache-dir --disable-pip-version-check --root-user-action=ignore -q -r requirements.txt
    echo "v2:$HASH" > /app/.orbital/reqs.ok
  fi
fi
echo "[synkrone] starting bot"
exec python -u main.py
