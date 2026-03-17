# Data Flow Diagrams — gitDeploy

All diagrams use ASCII-art notation following standard structured-analysis DFD conventions.

**Notation key:**

```
[ Entity Name ]        External entity (data source or sink — lives outside the system boundary)
( Process Name )       Process (transforms or routes data)
=== Store Name ===     Data store (persistent storage)
-->                    Data flow with label
```

---

## Level 0 — Context Diagram

The context diagram shows gitDeploy as a single system with all external entities that interact with it.

```
                                ┌──────────────────────────────────────┐
                                │                                      │
  [ User / Browser ] ──────────>│                                      │──────────> [ User / Browser ]
  credentials, app config       │                                      │  tokens, app status, metrics
                                │                                      │
  [ Admin / Browser ] ─────────>│          gitDeploy System            │──────────> [ Admin / Browser ]
  admin commands                │                                      │  system health, user/app data
                                │                                      │
  [ GitHub API ] ──────────────>│                                      │──────────> [ GitHub / Git CLI ]
  repo metadata (JSON)          │                                      │  clone/pull requests
                                │                                      │
  [ Docker Daemon ] ───────────>│                                      │──────────> [ Docker Daemon ]
  build output, run status      │                                      │  build, run, rm commands
                                │                                      │
  [ Nginx ] ───────────────────>│                                      │──────────> [ Nginx ]
  (reads conf files)            │                                      │  server block config files
                                │                                      │
  [ Cloudflare Tunnel ] ───────>│                                      │──────────> [ Cloudflare Tunnel ]
  (routes public traffic)       │                                      │  tunnel config (manual/script)
                                │                                      │
  [ Redis ] ───────────────────>│                                      │──────────> [ Redis ]
  cached values                 │                                      │  get/set/delete cache ops
                                │                                      │
  [ Secret Sidecar :8001 ] ────>│                                      │──────────> [ Secret Sidecar :8001 ]
  decrypted secrets             │                                      │  store/retrieve/rotate requests
                                │                                      │
                                └──────────────────────────────────────┘
```

---

## Level 1 — Main Process Decomposition

The system is decomposed into four major processes.

```
                         ┌────────────────────────────────────────────────────────────────────┐
                         │                       gitDeploy System                              │
                         │                                                                      │
[ User ]                 │  ┌────────────────┐                                                  │
    |                    │  │                │   user record,          ┌══════════════════┐     │
    | credentials        │  │  P1            │   hashed password  ─── │  === users DB ===│     │
    |──────────────────> │  │  Authentication│ <─────────────────────> │                  │     │
    |                    │  │  & Auth Mgmt   │                         └══════════════════┘     │
    | access_token,      │  │                │                                                  │
    | refresh_cookie <── │  └────────────────┘                                                  │
    |                    │         |                                                             │
    |                    │         | authenticated_user                                          │
    |                    │         v                                                             │
    | app config,        │  ┌────────────────┐         git clone/pull  ┌══════════════════┐     │
    | repo_url, env ───> │  │                │ ─────────────────────── │ === apps DB    ===│     │
    |                    │  │  P2            │ <────────────────────── │                  │     │
    | deploy status,     │  │  App           │         app records     └══════════════════┘     │
    | app detail  <───── │  │  Management    │                                                  │
    |                    │  │                │ ─────────────────────── [ GitHub API ]            │
    |                    │  └───────┬────────┘ validate repo_url                                │
    |                    │         |                                                             │
    |                    │         | deploy_request                                              │
    |                    │         v                                                             │
    |                    │  ┌────────────────┐         docker cmds     ┌══════════════════┐     │
    |                    │  │                │ ─────────────────────── │ === file system ==│     │
    |                    │  │  P3            │         git cmds        │ /opt/apps/{id}   │     │
    |                    │  │  Deployment    │ ─────────────────────── │ /opt/logs/{id}   │     │
    |                    │  │  Pipeline      │                         └══════════════════┘     │
    |                    │  │                │ ─── write conf ──────── [ Nginx config dir ]      │
    |                    │  └───────┬────────┘                                                  │
    |                    │         |                                                             │
    |                    │         | error_events                                                │
    |                    │         v                                                             │
    |                    │  ┌──────────────────┐                       ┌══════════════════┐     │
    |                    │  │                  │ ─────────────────────>│ === error_logs ===│     │
    |                    │  │  P4 Error Logger │                       │                  │     │
    |                    │  │                  │                       └══════════════════┘     │
    |                    │  └──────────────────┘                                                │
    |                    │                                                                      │
[ Admin ]               │  ┌────────────────┐         reads all       ┌══════════════════┐     │
    |                    │  │                │ <────────────────────── │  === users DB ===│     │
    | admin requests ──> │  │  P5            │ <────────────────────── │  === apps DB  ===│     │
    |                    │  │  Admin         │ <────────────────────── │  === error_logs==│     │
    | health, data <──── │  │  Control Plane │                         └══════════════════┘     │
    |                    │  │                │ ─── psutil calls ─────── [ OS / Host ]            │
    |                    │  └────────────────┘                                                  │
    |                    │                                                                      │
                         └────────────────────────────────────────────────────────────────────┘
```

---

## Level 2 — Deployment Pipeline (P3) Detail

This diagram expands Process P3 (Deployment Pipeline) into its sub-processes.

```
                  ┌───────────────────────────────────────────────────────────────────────┐
                  │                   P3 — Deployment Pipeline                             │
                  │                                                                         │
  deploy_request  │  ┌─────────────────┐                                                   │
  (app_id, opts)  │  │                 │                                                   │
  ──────────────> │  │  P3.1           │  app_record        ┌═══════════════════════════┐  │
                  │  │  Load & Validate│ ─────────────────> │ === apps DB            === │  │
                  │  │  App Record     │ <───────────────── │                            │  │
                  │  │                 │  app_data          └═══════════════════════════┘  │
                  │  └────────┬────────┘                                                   │
                  │           │ app_data + override_params                                  │
                  │           v                                                              │
                  │  ┌─────────────────┐                                                   │
                  │  │                 │  validate_url       ┌══════════════════┐           │
                  │  │  P3.2           │ ─────────────────── [ GitHub API     ]            │
                  │  │  Git: Clone or  │ <─────────────────── repo_metadata                │
                  │  │  Pull Source    │                                                   │
                  │  │                 │  clone/pull cmds    ┌══════════════════════════┐  │
                  │  │                 │ ─────────────────── [ Git CLI             ]     │  │
                  │  │                 │ <─────────────────── exit_code, stderr          │  │
                  │  │                 │                      └══════════════════════════┘  │
                  │  │                 │  write .env          ┌══════════════════════════┐  │
                  │  │                 │ ─────────────────── │ === /opt/apps/{id}/.env ===│  │
                  │  └────────┬────────┘                      └══════════════════════════┘  │
                  │           │ source_ready                                                 │
                  │           v                                                              │
                  │  ┌─────────────────┐  status=prepared    ┌═══════════════════════════┐  │
                  │  │  P3.3           │ ─────────────────── │ === apps DB            === │  │
                  │  │  Update Status  │                     └═══════════════════════════┘  │
                  │  │  PREPARED       │                                                   │
                  │  └────────┬────────┘                                                   │
                  │           │                                                              │
                  │           v                                                              │
                  │  ┌─────────────────┐                                                   │
                  │  │                 │  build command       ┌══════════════════════════┐  │
                  │  │  P3.4           │ ─────────────────── [ Docker Daemon         ]   │  │
                  │  │  Docker Build   │ <─────────────────── streaming build output      │  │
                  │  │                 │                      └══════════════════════════┘  │
                  │  │                 │  Dockerfile path     ┌══════════════════════════┐  │
                  │  │                 │ ─────────────────── │ === /opt/apps/{id}/      ===│  │
                  │  └────────┬────────┘                      └══════════════════════════┘  │
                  │           │ image_name:tag                                               │
                  │           v                                                              │
                  │  ┌─────────────────┐  query used ports   ┌═══════════════════════════┐  │
                  │  │                 │ ─────────────────── │ === apps DB            === │  │
                  │  │  P3.5           │ <─────────────────── used_ports_set                │
                  │  │  Allocate Port  │                     └═══════════════════════════┘  │
                  │  │  10000-65535    │  socket.bind(port)   [ OS socket layer        ]    │
                  │  │                 │ ─────────────────── (check each candidate)          │
                  │  │                 │ <─────────────────── OSError or success             │
                  │  └────────┬────────┘                                                   │
                  │           │ free_port                                                    │
                  │           v                                                              │
                  │  ┌─────────────────┐                                                   │
                  │  │                 │  docker run cmd      ┌══════════════════════════┐  │
                  │  │  P3.6           │ ─────────────────── [ Docker Daemon         ]   │  │
                  │  │  Docker Run     │ <─────────────────── container_id / stderr        │  │
                  │  │  Container      │                      └══════════════════════════┘  │
                  │  └────────┬────────┘                                                   │
                  │           │ container_id                                                 │
                  │           v                                                              │
                  │  ┌─────────────────┐  status=running      ┌═══════════════════════════┐ │
                  │  │  P3.7           │ ─────────────────── │ === apps DB            === │ │
                  │  │  Update Status  │  internal_port saved  └═══════════════════════════┘ │
                  │  │  RUNNING        │                                                   │
                  │  └────────┬────────┘                                                   │
                  │           │                                                              │
                  │           v                                                              │
                  │  ┌─────────────────┐  write conf file     ┌══════════════════════════┐  │
                  │  │  P3.8           │ ─────────────────── │ /etc/nginx/gitdeploy.d/  ===│  │
                  │  │  Write Nginx    │  nginx -s reload     │ app-{id}.conf             │  │
                  │  │  Config         │ ─────────────────── [ Nginx Process          ]   │  │
                  │  └─────────────────┘                      └══════════════════════════┘  │
                  │                                                                         │
                  └───────────────────────────────────────────────────────────────────────┘
```

---

## Level 2 — Authentication Flow (P1) Detail

```
                  ┌─────────────────────────────────────────────────────────┐
                  │               P1 — Authentication & Auth Mgmt            │
                  │                                                           │
  credentials     │  ┌─────────────────┐  lookup user     ┌═══════════════┐  │
  ──────────────> │  │  P1.1           │ ──────────────── │ === users DB  │  │
                  │  │  Verify         │ <──────────────── user_record      │  │
                  │  │  Credentials    │                  └═══════════════┘  │
                  │  │  (bcrypt check) │                                     │
                  │  └────────┬────────┘                                     │
                  │           │ authenticated_user                            │
                  │           v                                               │
                  │  ┌─────────────────┐                                     │
                  │  │  P1.2           │  access_token (JWT, 15 min)  ──────>│ ──> [ User ]
                  │  │  Generate       │  refresh_token (JWT, 7 days) ──────>│ ──> [ Cookie store ]
                  │  │  Tokens         │                                     │
                  │  └─────────────────┘                                     │
                  │                                                           │
  refresh_cookie  │  ┌─────────────────┐  decode + verify  [ JWT secret ]   │
  ──────────────> │  │  P1.3           │  lookup user     ┌═══════════════┐  │
                  │  │  Refresh Token  │ ──────────────── │ === users DB  │  │
                  │  │  Validation     │ <──────────────── user_record      │  │
                  │  │                 │                  └═══════════════┘  │
                  │  │                 │  new_access_token ──────────────── >│ ──> [ User ]
                  │  └─────────────────┘                                     │
                  │                                                           │
  access_token    │  ┌─────────────────┐  decode + verify  [ JWT secret ]   │
  ──────────────> │  │  P1.4           │  lookup user     ┌═══════════════┐  │
                  │  │  Bearer Token   │ ──────────────── │ === users DB  │  │
                  │  │  Validation     │ <──────────────── user_record      │  │
                  │  │  (per request)  │                  └═══════════════┘  │
                  │  │                 │  current_user ─────────────────────>│ ──> (downstream process)
                  │  └─────────────────┘                                     │
                  │                                                           │
                  └─────────────────────────────────────────────────────────┘
```

---

## Data Dictionary

| Data Flow Label          | Contents                                                                                  |
|--------------------------|-------------------------------------------------------------------------------------------|
| `credentials`            | `{email: str, password: str}`                                                              |
| `access_token`           | HS256 JWT: `{sub, username, role, exp, type="access"}`                                    |
| `refresh_cookie`         | HttpOnly cookie: HS256 JWT `{sub, exp, type="refresh"}`, path=/api/v1/auth/refresh        |
| `app_config`             | `{name, repo_url, container_port, branch, dockerfile_path, source_dir, env}`              |
| `deploy_request`         | `{branch?, dockerfile_path?, source_dir?, env?, build_args?, force_rebuild?, clear_cache?}`|
| `app_record`             | Full `AppModel` row including `id, name, subdomain, status, internal_port, ...`           |
| `deploy status`          | `{id: int, status: "running"|"error"}`                                                    |
| `repo_metadata`          | GitHub API `/repos/{owner}/{repo}` JSON: `{private: bool, ...}`                           |
| `error_event`            | `{error_code, status_code, app_id?, context?}`                                            |
| `system_metrics`         | `{cpu: {...}, memory: {...}, disk: {...}, network: {...}, uptime_seconds, apps: {...}, users: {...}}` |
| `conf_file`              | Nginx server block text for `app-{id}.APP_DOMAIN`                                         |
| `secrets_payload`        | `{secrets: {KEY: VALUE, ...}}` — sent to sidecar, stored encrypted                        |
