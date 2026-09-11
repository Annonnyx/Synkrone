# Filesystem

`FilesystemManager(type, serviceId)` resolves everything under
`${DATA_ROOT}/{type}/{serviceId}`:

`list read write mkdir delete rename move copy upload download zip unzip`

Protections: `..` segments rejected, resolved path must stay under the root, and
`realpath` must also stay under the root (symlink escape). The service root is
derived from the authenticated service row — never from user input.

API: `GET/POST/DELETE /api/services/:id/files` with `op=list|read|download|archive`
(GET) and `op=write|mkdir|rename|copy|unzip` or multipart upload (POST).
