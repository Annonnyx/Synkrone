# Workers

`service-worker`, `deployment-worker` and `backup-worker` all execute the same
job bodies exported by `src/lib/jobs/handlers.ts` against the Postgres-backed
queue in `src/lib/jobs/queue.ts`:

| Worker             | Job types                                              |
| ------------------ | ------------------------------------------------------ |
| service-worker     | CREATE_CONTAINER, DELETE_CONTAINER, INSTALL_MINECRAFT   |
| deployment-worker  | DEPLOY_WEB, CLONE_GITHUB, INSTALL_ADDON                 |
| backup-worker      | CREATE_BACKUP, RESTORE_BACKUP                           |

In the single-node default the control API runs the same code in-process
(`dispatch(...)`), so progress reporting is identical whichever runner picks up
the job.
