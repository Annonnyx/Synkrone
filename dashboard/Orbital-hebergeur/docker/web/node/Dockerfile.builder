# Ephemeral build container (§34): build tools never run in the runtime container.
FROM node:20.18-alpine3.20
WORKDIR /build
COPY . .
RUN npm ci --no-audit --no-fund && npm run build --if-present
# Artifacts are copied out to the service volume by the deployment worker.
