# Integration / E2E suites

These require a live Docker daemon and a Postgres instance:

1. **auth** – register, login, session cookie, API key bearer auth, 401/403 paths.
2. **authorization** – user A cannot read/act on user B's service (404), viewer
   cannot start a container (403).
3. **container creation** – POST /api/services creates volume + container, job
   steps reach 100%, `docker inspect` shows the expected image and limits.
4. **isolation** – two services get two containers, two volumes, two networks.
5. **resource limits** – `Memory` and `NanoCpus` match the requested values.
6. **filesystem** – upload, edit, download, traversal rejection.
7. **console** – SSE stream emits container stdout, commands reach the process.
8. **database** – provisioning creates a role limited to its database.
9. **GitHub deploy** – clone, build, new container version, rollback.
10. **Minecraft install** – eula, server.properties, plugin upload.
11. **Discord bot launch** – token injection, login, slash command registration.
