# Databases

`DatabaseManager` provisions a **real** database per request:

```sql
CREATE ROLE  orb_<name>_<rand>_u LOGIN PASSWORD '<generated>';
CREATE DATABASE orb_<name>_<rand> OWNER orb_<name>_<rand>_u;
REVOKE ALL ON DATABASE ... FROM PUBLIC;
```

One database ⇒ one dedicated user ⇒ no cross-project access. The connection
string is injected as an encrypted `DATABASE_URL` env var for the attached
service and displayed once in the UI. Password reset issues a real `ALTER ROLE`.
