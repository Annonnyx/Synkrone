# Tests

`tests/` contains runnable Node test-runner suites (`npm run test`):

* `crypto.test.ts` – AES-GCM round trip, password hashing, fingerprints.
* `filesystem.test.ts` – traversal, absolute escape, symlink escape, CRUD, archive.
* `docker-policy.test.ts` – the adapter refuses privileged/host-network/rogue
  binds and always emits Memory + NanoCpus limits and dropped capabilities.
* `templates.test.ts` – runtime family isolation (one image family per type) and
  intent computation.

Integration/E2E suites (authentication, container creation, console, uploads,
GitHub deployment) require a live Docker daemon and are described in
`tests/integration.md`.

Run them with:

```bash
node --experimental-strip-types --import ./tests/support/alias.mjs --test "tests/*.test.ts"
```
