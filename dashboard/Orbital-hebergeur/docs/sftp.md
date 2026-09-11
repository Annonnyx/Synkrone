# SFTP

Each service receives an account at creation time:

```
Host: $SFTP_HOST   Port: 2022   Username: <type>_<slug>_<id6>   Chroot: /data/<type>/<id>
```

Passwords are generated server-side, stored encrypted and shown once on rotation.
`SFTPManager.sync()` renders `${DATA_ROOT}/sftp/users.conf`, the account file the
`sftp` gateway container (atmoz/sftp) consumes. Each account is chrooted to a
single service volume.
