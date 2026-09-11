# Docker layer

## Three separate runtime families

`docker/discord`, `docker/minecraft/*`, `docker/web/*` — separate Dockerfiles,
separate base images, separate entrypoints, separate networks and separate
volume mount points. A service of one family can never be scheduled on the image
of another: the provider decides the template, the API only knows the serviceId.

## Container spec policy (src/lib/docker/adapter.ts)

Built server-side from a validated description. Structurally impossible:

* `Privileged`, `CapAdd`, `--network host`, `/dev/*` devices
* binds outside the platform data root, docker socket mounts
* host ports below 1024, CPU > 16 cores, memory > 64GB

Always applied: `CapDrop: ALL`, `no-new-privileges`, `PidsLimit`, tmpfs `/tmp`,
json-file log rotation, `User 1000:1000`, `Memory`, `MemorySwap`, `NanoCpus`.

## Lifecycle states

`CREATING STARTING RUNNING STOPPING STOPPED RESTARTING CRASHED ERROR DELETING` —
derived from a real `docker inspect` and persisted on the `services` /
`containers` rows (the database, not Docker, is the source of truth for the link
between a service and its container).
