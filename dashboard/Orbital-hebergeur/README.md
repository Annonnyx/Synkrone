# Orbital — universal containerised service platform

Create, deploy and administer **Discord bots**, **Minecraft servers** and **web
apps** from one panel. Every service gets its **own Docker container, own volume,
own network and real cgroup resource limits**.

```
Dashboard -> Control API -> Service Manager -> Runtime Provider -> Dedicated container
```

The frontend never talks to Docker. Only the control API holds the socket.

## Runtime families

| Family    | Images (docker/)                                             | Volume                     | Network            |
| --------- | ------------------------------------------------------------ | -------------------------- | ------------------ |
| Discord   | `discord-runtime`                                             | `/data/discord/{id}` → /app | `orbital-discord`  |
| Minecraft | `minecraft-{paper,fabric,forge,neoforge,vanilla}-runtime`      | `/data/minecraft/{id}` → /data | `orbital-minecraft` |
| Web       | `web-{static,node,react,next}`                                 | `/data/web/{id}` → /srv/app | `orbital-web` + `orbital-proxy` |

## Quick start (single node)

```bash
cp .env.example .env          # set PLATFORM_SECRET_KEY
docker compose up -d          # postgres, redis, panel, traefik, sftp
npm run db:push               # create the schema
```

Then open the panel, register, and create a service. Provisioning steps
(volume → files → image pull → container create → start) are reported live by the
worker.

## Running the panel from source

From the **Synkrone repo root**, `npm start` launches the public site and this
panel together (`http://127.0.0.1:3668/hebergement`). Postgres is required.

```bash
npm install
cp .env.example .env
# generate a master key for secret encryption:
node -e "console.log(require('crypto').randomBytes(48).toString('base64url'))"

# a Postgres instance is the only hard requirement:
docker run -d --name orbital-postgres -p 5432:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=app_db \
  postgres:16-alpine

npm run db:push               # create the schema
```

The first account you register through `/login` becomes a regular user; there is
no seeding step and no demo data.

Useful scripts: `npm run build`, `npm run lint`, `npm run typecheck`,
`npm run test` (see `docs/testing.md`).

### Container engines

The control API speaks the Docker Engine API, so either engine works:

| Engine            | `DOCKER_SOCKET`                       |
| ----------------- | ------------------------------------- |
| Docker            | `/var/run/docker.sock`                |
| Podman (rootless) | `/run/user/$UID/podman/podman.sock`   |

Podman needs its API socket enabled once with
`systemctl --user enable --now podman.socket`. Rootless Podman gives containers a
private uid range, so the platform detects it and maps the volume owner with
`keep-id`; on SELinux hosts the volume bind is relabelled automatically.

### Local development without a container engine

The panel runs fine without a daemon: filesystem manager, configuration,
databases, backups, audit and the console history all work. Container lifecycle
calls return a real `503 DOCKER_UNAVAILABLE` error instead of pretending to work —
there is no simulated state anywhere in the product.

## Documentation

`docs/architecture.md`, `docker.md`, `security.md`, `discord.md`, `minecraft.md`,
`web.md`, `database.md`, `filesystem.md`, `sftp.md`, `deployment.md`, `testing.md`.
