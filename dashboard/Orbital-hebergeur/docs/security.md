# Security

* **Secrets** – AES-256-GCM (`src/lib/crypto.ts`). Discord tokens and env values
  are encrypted at rest, never returned to the browser (only a fingerprint), and
  injected exclusively into the owning container.
* **Passwords** – scrypt with per-user salt; API keys stored as SHA-256 hashes.
* **Authorization** – `authorizeService()` is the single entry point; every file,
  container and log path is derived from the row it returns (owner or project
  member with a sufficient role: viewer < member < admin < owner).
* **Filesystem** – traversal, absolute escape and symlink escape rejected
  (`FilesystemManager.resolve`). A user can only reach their own service volume.
* **Docker** – only the control API mounts the socket (read-only). The frontend
  never receives Docker data it did not obtain through the API.
* **Rate limiting** – login/register and per-service action buckets.
* **Audit log** – user, action, service, result, IP, timestamp on every mutation.
* **OAuth** – authorization-code + PKCE + signed CSRF state cookie. Tokens are
  AES-256-GCM encrypted on `oauth_accounts` (`access_token_enc`,
  `refresh_token_enc`). Buttons stay visible but disabled when the provider
  client id/secret env vars are missing. Discord OAuth is for panel login, not
  bot tokens. GitHub tokens (scope `repo`) are used only to list/clone the
  owner's repositories and are never logged.
