# Web runtime

Templates: static (nginx), javascript, typescript, react, next, node.
Extensible: add an entry to `WEB_TEMPLATES` + a Dockerfile in `docker/web/`.

Pipeline (`DEPLOY_WEB` job, real logs per step):

```
Fetch source (git clone --depth 1 --branch <branch>)
  -> install/build commands (delegated to the runtime container or the builder image)
  -> remove previous container version
  -> create new container version
  -> start
```

Every deployment is a row (`deployments`) with number, trigger, commit, logs and
`isCurrent`; rollback creates a new deployment from an older one.
GitHub import requires a linked GitHub account (`Compte → Profil`). The panel
lists repositories with the stored token and clones via `x-access-token` without
logging credentials. Push webhooks (`/api/webhooks/github/{serviceId}`) verify
the HMAC-SHA256 signature before triggering an automatic deployment.

Domains:

* Suggested hostname `{slug}.{ORBITAL_PUBLIC_DOMAIN}` (placeholder `example.com`
  until a real domain is purchased).
* Custom hostnames persist on `domains` and show CNAME / A / AAAA records
  targeting `ORBITAL_PUBLIC_HOST` / `ORBITAL_PUBLIC_IP`.
* When `ORBITAL_TRAEFIK_DYNAMIC_DIR` (or `docker/proxy/dynamic`) is writable,
  a file router is generated: hostname → `web-{slug}-{id}` → container port.
