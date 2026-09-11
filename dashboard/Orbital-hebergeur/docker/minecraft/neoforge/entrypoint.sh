#!/bin/bash
set -e
cd /data
mkdir -p mods config logs
case "$SERVER_FAMILY" in
  fabric)
    [ -f fabric-installer.jar ] || curl -fsSL -o fabric-installer.jar "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar"
    [ -f fabric-server-launch.jar ] || java -jar fabric-installer.jar server -mcversion "$MC_VERSION" -downloadMinecraft
    LAUNCH=fabric-server-launch.jar ;;
  forge|neoforge)
    LAUNCH=$(ls *forge*server*.jar 2>/dev/null | head -n1)
    if [ -z "$LAUNCH" ]; then echo "[orbital] place the ${SERVER_FAMILY} installer jar in the volume"; sleep 5; exit 70; fi ;;
  *)
    [ -f server.jar ] || curl -fsSL -o server.jar "https://piston-data.mojang.com/v1/objects/server.jar" || true
    LAUNCH=server.jar ;;
esac
exec java -Xms"${MEMORY}" -Xmx"${MEMORY}" -XX:+UseG1GC -jar "$LAUNCH" nogui
