# Orbital Discord Bot Runtime — registry.example.com/platform/discord-runtime:1.0
# Minimal, pinned, non-root Node.js LTS image dedicated to Discord bots ONLY.
FROM node:20.18-alpine3.20

RUN apk add --no-cache tini dumb-init \
 && addgroup -g 1000 -S bot 2>/dev/null || true \
 && adduser -u 1000 -S bot -G bot 2>/dev/null || true

WORKDIR /app
ENV NODE_ENV=production \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false

COPY --chown=1000:1000 boot.sh /usr/local/bin/orbital-boot
RUN chmod +x /usr/local/bin/orbital-boot

# Bot sources live in the mounted volume /app (one volume per service).
USER 1000:1000
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/usr/local/bin/orbital-boot"]
