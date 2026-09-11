# Reverse proxy (Traefik)

Domains added in the panel are stored in the `domains` table and rendered into a
router definition here:

```
domain -> serviceId -> container (web-<slug>-<id>) -> port
```

Web containers only join `orbital-web` + `orbital-proxy`; they are never published
directly on the public interface.
