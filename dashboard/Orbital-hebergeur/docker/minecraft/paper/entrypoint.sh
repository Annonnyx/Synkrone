#!/bin/bash
set -e
cd /data
JAR="server.jar"
if [ ! -f "$JAR" ]; then
  echo "[orbital] downloading ${SERVER_FAMILY} ${MC_VERSION}"
  case "$SERVER_FAMILY" in
    paper|spigot)
      BUILD=$(curl -s "https://api.papermc.io/v2/projects/paper/versions/${MC_VERSION}" | sed 's/.*,\([0-9]*\)]}/\1/')
      curl -fsSL -o "$JAR" "https://api.papermc.io/v2/projects/paper/versions/${MC_VERSION}/builds/${BUILD}/downloads/paper-${MC_VERSION}-${BUILD}.jar" ;;
    purpur)
      curl -fsSL -o "$JAR" "https://api.purpurmc.org/v2/purpur/${MC_VERSION}/latest/download" ;;
  esac
fi
mkdir -p plugins logs
exec java -Xms"${MEMORY}" -Xmx"${MEMORY}" -XX:+UseG1GC -jar "$JAR" nogui
