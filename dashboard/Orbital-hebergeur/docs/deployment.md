# Deployment

## Single node

`docker compose up -d` starts postgres, redis, the panel (control API + UI),
Traefik and the SFTP gateway. Set `PLATFORM_SECRET_KEY` and `RUNTIME_IMAGE_MODE`.

## Building the runtime images

```bash
docker build -t $REG/discord-runtime:1.0        docker/discord
docker build -t $REG/minecraft-paper-runtime:1.0 docker/minecraft/paper
docker build -t $REG/web-node:1.0                docker/web/node
docker push ...
export RUNTIME_IMAGE_MODE=registry RUNTIME_REGISTRY=$REG
```

## Multi node (roadmap)

Register nodes in the `nodes` table, point `services.nodeId` at the chosen node
and give the engine client that node's endpoint. The scheduler weighs CPU, RAM,
storage, node status and service requirements.
