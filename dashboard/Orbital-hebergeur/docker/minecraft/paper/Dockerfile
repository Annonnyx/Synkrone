# Orbital Minecraft Paper/Purpur/Spigot runtime (plugins family)
FROM eclipse-temurin:21.0.5_11-jre-alpine

RUN apk add --no-cache bash curl tini su-exec \
 && adduser -u 1000 -S minecraft -G users
ENV SERVER_FAMILY=paper MC_VERSION=1.21.1 MEMORY=2G
WORKDIR /data
COPY entrypoint.sh /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint
USER 1000:100
EXPOSE 25565/tcp 19132/udp
ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/entrypoint"]
