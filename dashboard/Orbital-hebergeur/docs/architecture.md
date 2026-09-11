# Architecture

```
Frontend (Next.js App Router, RSC + client panels)
        |  fetch / SSE
Control API (route handlers, auth + authorization + audit)
        |
Service managers (src/lib/services, src/lib/jobs)
        |
Runtime providers (Discord / Minecraft / Web)  -- src/lib/runtime/*
        |
DockerAdapter + ContainerManager (policy layer) -- src/lib/docker/adapter.ts
        |
Docker Engine API client (unix socket)          -- src/lib/docker/engine.ts
```

## Why this stack

* **Next.js route handlers as the control API** – one deployable, one auth layer,
  server-only modules (`node:http`, `node:fs`) are never bundled to the browser.
* **Drizzle + PostgreSQL** instead of Prisma – no generate step, fully typed SQL
  and the same client can provision per-project databases.
* **Postgres job queue** instead of Redis/BullMQ – transactional with the domain
  data and zero extra infra for a single node. `workers/` documents how the same
  job bodies run out-of-process; Redis is already in the compose file for a
  future BullMQ driver.
* **SSE for consoles** – authenticated, proxy friendly, auto-reconnecting. The
  route (`GET /api/services/:id/stream`) performs authentication, authorization
  and ownership checks *before* the stream is opened, exactly like the WebSocket
  contract in the spec.

## Multi-node readiness

`nodes` table + `services.nodeId` + `ComputeNode` capacity fields already exist.
A scheduler only needs to choose a node row and point the engine client at that
node's endpoint (`nodes.dockerEndpoint`); nothing else in the stack assumes a
local daemon.
