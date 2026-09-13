# SFTP

Each service receives an account at creation time:

```
Host: $SFTP_HOST   Port: 2022   Username: <type>_<slug>_<id6>   Chroot: /data/<type>/<id>
```

A strong password is generated per service (not the Synkrone account password — OAuth users have none). It is stored encrypted and shown once at creation and on regenerate. Regenerating invalidates the previous password.

`SFTPManager.sync()` renders `${DATA_ROOT}/sftp/users.conf`, the account file the
`sftp` gateway container (atmoz/sftp) consumes. Each account is chrooted to a
single service volume.
