# Orbital web-node runtime — runtime container only (builds happen in the builder image).
FROM node:20.18-alpine3.20
RUN apk add --no-cache tini
WORKDIR /srv/app
ENV NODE_ENV=production PORT=3000
USER 1000:1000
EXPOSE 3000
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["sh", "/srv/app/.orbital/start.sh"]
