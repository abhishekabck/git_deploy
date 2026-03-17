# UML Diagrams — gitDeploy

All diagrams are represented in plain ASCII art following standard UML notation conventions. They can be read without any tooling.

---

## 1. Class Diagram

Shows the ORM model classes, their attributes, types, and relationships.

```
┌──────────────────────────────────────┐
│              <<model>>               │
│               Users                  │
├──────────────────────────────────────┤
│  + id            : Integer  [PK]     │
│  + username      : String   [UNIQUE] │
│  + email         : String   [UNIQUE] │
│  + hashed_password : String          │
│  + role          : Enum(UserRoles)   │
│  + billing_type  : Enum(BillingType) │
│  + created_at    : DateTime          │
│  + updated_at    : DateTime          │
├──────────────────────────────────────┤
│  (inherits TimeStatusMixin)          │
└──────────────────────────────────────┘
                   |
                   | 1
                   |
                   | (user_id FK)
                   |
                   * many
┌──────────────────────────────────────┐
│              <<model>>               │
│              AppModel                │
├──────────────────────────────────────┤
│  + id              : Integer [PK]    │
│  + name            : String          │
│  + subdomain       : Text   [UNIQUE] │
│  + repo_url        : String          │
│  + internal_port   : Integer [NULL]  │
│  + container_port  : Integer         │
│  + branch          : String          │
│  + build_path      : String          │
│  + dockerfile_path : String          │
│  + status          : Enum(AppStatus) │
│  + env             : JSON            │
│  + user_id         : Integer [FK]    │
│  + created_at      : DateTime        │
│  + updated_at      : DateTime        │
├──────────────────────────────────────┤
│  CHECK: container_port IN [1024,65535]│
│  (inherits TimeStatusMixin)          │
└──────────────────────────────────────┘


┌──────────────────────────────────────┐
│              <<model>>               │
│              ErrorLog                │
├──────────────────────────────────────┤
│  + id           : Integer [PK]       │
│  + error_code   : String  [INDEX]    │
│  + status_code  : Integer            │
│  + app_id       : Integer [NULL,IDX] │
│  + context      : Text    [NULL]     │
│  + created_at   : DateTime (UTC)     │
└──────────────────────────────────────┘
  (app_id references AppModel.id — soft ref, no FK constraint)


┌──────────────────────────────────────┐
│              <<model>>               │
│            SecretStore               │
│          (sidecar database)          │
├──────────────────────────────────────┤
│  + id                 : Integer [PK] │
│  + app_id             : Integer [UQ] │
│  + encrypted_secrets  : Text         │
└──────────────────────────────────────┘
  (references AppModel.id conceptually — different DB)


┌──────────────────────────────────────┐
│             <<mixin>>                │
│          TimeStatusMixin             │
├──────────────────────────────────────┤
│  + created_at : DateTime             │
│  + updated_at : DateTime             │
└──────────────────────────────────────┘

<<enum>> AppStatus          <<enum>> UserRoles      <<enum>> BillingType
─────────────────           ──────────────────      ────────────────────
CREATED  = "created"        USER  = "user"          FREE = "free"
PREPARED = "prepared"       ADMIN = "admin"         PAID = "paid"
RUNNING  = "running"
ERROR    = "error"
```

---

## 2. Sequence Diagram — App Deployment Flow

Shows the message sequence for a `POST /api/v1/apps/{id}/deploy` call from start to completion.

```
Client          FastAPI          deploy.py       docker.py      port_manager    Nginx Mgr       DB
  |                |                 |               |               |               |            |
  |─── POST ──────>|                 |               |               |               |            |
  |  /apps/{id}/   |                 |               |               |               |            |
  |  deploy        |── get_db ──────────────────────────────────────────────────────────────────>|
  |                |<─ AsyncSession ─────────────────────────────────────────────────────────────|
  |                |                 |               |               |               |            |
  |                |── _get_owned_app ──────────────────────────────────────────────────────────>|
  |                |<─ AppModel ─────────────────────────────────────────────────────────────────|
  |                |                 |               |               |               |            |
  |                |── to_thread ───>|               |               |               |            |
  |                |  clone_or_pull  |               |               |               |            |
  |                |                 |─── validate_github_repo ─────>                            |
  |                |                 |   (GitHub API call, sync)                                 |
  |                |                 |<─ valid / error                                            |
  |                |                 |                                                            |
  |                |                 |─── git clone / git pull ──────────────────────────────>  [Git CLI]
  |                |                 |<── exit_code                                           <  [Git CLI]
  |                |                 |                                                            |
  |                |<─ returned ─────|               |               |               |            |
  |                |── status=PREPARED ─────────────────────────────────────────────────────────>|
  |                |── db.commit ───────────────────────────────────────────────────────────────>|
  |                |                 |               |               |               |            |
  |                |── to_thread ───────────────────>|               |               |            |
  |                |  docker_build   |               |               |               |            |
  |                |                 |               |─── switch_to_branch ─────────────────> [Git CLI]
  |                |                 |               |<── exit_code                          < [Git CLI]
  |                |                 |               |                                           |
  |                |                 |               |─── subprocess.Popen(docker build) ────> [Docker]
  |                |                 |               |  (streams stdout line by line to logger)  |
  |                |                 |               |<── exit_code                          < [Docker]
  |                |                 |               |                                           |
  |                |<─ returned ─────────────────────|               |               |            |
  |                |── to_thread ───────────────────────────────────>|               |            |
  |                |  allocate_free_port                              |               |            |
  |                |                                                  |── SELECT internal_port ──>|
  |                |                                                  |<─ used_ports_set ─────────|
  |                |                                                  |── socket.bind(port) ── [OS]
  |                |                                                  |<─ free or OSError ─── [OS]
  |                |<─ free_port ─────────────────────────────────────|               |            |
  |                |── app.internal_port = free_port ──────────────────────────────────────────>  |
  |                |── db.commit ───────────────────────────────────────────────────────────────>|
  |                |                 |               |               |               |            |
  |                |── to_thread ───────────────────>|               |               |            |
  |                |  docker_run     |               |               |               |            |
  |                |                 |               |─── subprocess.run(docker run) ─────────> [Docker]
  |                |                 |               |<── container_id / stderr              < [Docker]
  |                |<─ returned ─────────────────────|               |               |            |
  |                |── status=RUNNING ──────────────────────────────────────────────────────────>|
  |                |── db.commit ───────────────────────────────────────────────────────────────>|
  |                |                 |               |               |               |            |
  |                |── write_app_conf ──────────────────────────────────────────────>|            |
  |                |  (if NGINX_ENABLED)                                              |── write ─> [Nginx conf dir]
  |                |                                                                  |── reload ─>[nginx -s reload]
  |                |<─ returned ──────────────────────────────────────────────────────            |
  |                |                 |               |               |               |            |
  |<── 201 ────────|                 |               |               |               |            |
  |  {id, status:  |                 |               |               |               |            |
  |   "running"}   |                 |               |               |               |            |
```

---

## 3. Sequence Diagram — Authentication Flow

Shows the full JWT lifecycle: register, login, protected request, token refresh, and logout.

```
Client                FastAPI /auth              DB                Cookie Store
  |                        |                     |                      |
  |─── POST /register ────>|                     |                      |
  |  {username,email,pw}   |── SELECT user ─────>|                      |
  |                        |<─ None (no conflict)|                      |
  |                        |── hash(password) ───────── bcrypt ─────────|
  |                        |── INSERT user ──────>|                     |
  |<── 201 {user profile} ─|                     |                      |
  |                        |                     |                      |
  |─── POST /login ────────>|                    |                      |
  |  {email, password}     |── SELECT user ─────>|                      |
  |                        |<─ user_record        |                      |
  |                        |── bcrypt.verify ─────────── bcrypt ─────────|
  |                        |── create_access_token (HS256, 15min)        |
  |                        |── create_refresh_token (HS256, 7days)       |
  |                        |── Set-Cookie: refresh_token=... ───────────>|
  |<── 200 {access_token} ─|                     |                      |
  |                        |                     |                      |
  |─── GET /apps/list/ ────>|                    |                      |
  |  Bearer: access_token  |── decode_token ─────────── JWT verify ──── |
  |                        |── SELECT user ─────>|                      |
  |                        |<─ user_record        |                      |
  |                        |── SELECT apps ──────>|                     |
  |                        |<─ apps_list          |                      |
  |<── 200 [app list] ─────|                     |                      |
  |                        |                     |                      |
  | (15 minutes later — access token expired)    |                      |
  |                        |                     |                      |
  |─── POST /refresh ──────>|                    |                      |
  |  Cookie: refresh_token ─────────────────────────────────────────── >|
  |                        |<── refresh_token ────────────────────────── |
  |                        |── decode_token (verify type=refresh)        |
  |                        |── SELECT user ─────>|                      |
  |                        |<─ user_record        |                      |
  |                        |── create_access_token (new, 15min)         |
  |<── 200 {access_token} ─|                     |                      |
  |                        |                     |                      |
  |─── POST /logout ───────>|                    |                      |
  |                        |── Set-Cookie: max_age=0 ──────────────────>|
  |<── 200 {message} ──────|                     |                      |
```

---

## 4. State Diagram — App Lifecycle

Shows the valid state transitions for an `AppModel` record.

```
                         ┌──────────────────────────────────────────────────┐
                         │                  App Lifecycle                    │
                         └──────────────────────────────────────────────────┘

                              POST /create (validate + save to DB)
                         ─────────────────────────────────────────>

                         ┌───────────┐
                         │           │
                         │  CREATED  │  App record saved.
                         │           │  No code cloned yet.
                         │           │  internal_port = NULL
                         └─────┬─────┘
                               │
                               │  POST /deploy called
                               │  git clone/pull succeeds
                               │
                               v
                         ┌───────────┐
                         │           │
                         │ PREPARED  │  Source code on disk.
                         │           │  Docker build in progress.
                         │           │  internal_port = NULL
                         └─────┬─────┘
                               │
                         ┌─────┴────────────────────────────────────────┐
                         │  docker build succeeds                        │  any step fails
                         │  port allocated                               │
                         │  docker run succeeds                          v
                         │  nginx config written              ┌──────────────────┐
                         │                                    │                  │
                         v                                    │     ERROR        │
                   ┌───────────┐                              │                  │
                   │           │                              │  Container may   │
                   │  RUNNING  │ <────── redeploy succeeds ── │  or may not be   │
                   │           │                              │  running.        │
                   │  Container│                              │  internal_port   │
                   │  up and   │                              │  may be NULL.    │
                   │  reachable│                              └──────────────────┘
                   └─────┬─────┘                                        │
                         │                                              │
                         │  POST /deploy called again                   │  POST /deploy called
                         │  (redeploy: pull, rebuild, restart)          │  (retry)
                         │                                              │
                         └──────────────────────────────────────────────┘

                         ┌───────────────────────────────────────────────┐
                         │  DELETE /delete/{id}                           │
                         │  (or admin DELETE /admin/apps/{id})            │
                         │  ─────────────────────────────────────────>   │
                         │  Container removed, image removed, files       │
                         │  deleted, nginx conf removed, DB row deleted   │
                         │  ─────────────────────────────────────────>   │
                         │                (terminal — no state)           │
                         └───────────────────────────────────────────────┘

Admin PATCH /admin/apps/{id} can set status to any value directly.
```

---

## 5. Component Diagram

Shows the major runtime components and their communication paths.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   Host Server                                    │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                           gitDeploy API Process (:8000)                    │ │
│  │                                                                             │ │
│  │  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐ │ │
│  │  │  FastAPI   │  │  Auth        │  │  Deploy Service  │  │  Admin       │ │ │
│  │  │  Router    │─>│  Service     │  │  (git + docker)  │  │  Service     │ │ │
│  │  │  /api/v1   │  │  (JWT/bcrypt)│  │                  │  │  (psutil)    │ │ │
│  │  └────────────┘  └──────────────┘  └──────────────────┘  └──────────────┘ │ │
│  │         │                                    │                              │ │
│  │         │                                    │                              │ │
│  │  ┌──────▼────────────────────────────────────▼──────────────────────────┐  │ │
│  │  │              SQLAlchemy 2.0 Async ORM (aiosqlite / asyncpg)          │  │ │
│  │  └───────────────────────────────────────────────────────────────────────┘  │ │
│  │         │                                    │                              │ │
│  │  ┌──────▼──────┐                  ┌──────────▼───────────┐                  │ │
│  │  │  Port Mgr   │                  │  Nginx Manager       │                  │ │
│  │  │  (socket    │                  │  (write/remove conf, │                  │ │
│  │  │   bind)     │                  │   reload)            │                  │ │
│  │  └─────────────┘                  └──────────────────────┘                  │ │
│  │         │                                    │                              │ │
│  │  ┌──────▼──────┐                             │                              │ │
│  │  │  Redis Svc  │                             │                              │ │
│  │  │  (optional) │                             │                              │ │
│  │  └─────────────┘                             │                              │ │
│  └──────────────────────────────────────────────┼─────────────────────────────┘ │
│            │             │            │          │                               │
│            │             │            │          │                               │
│  ┌─────────▼──┐  ┌───────▼──┐  ┌─────▼────┐  ┌─▼───────────────────────┐      │
│  │  SQLite or  │  │  Redis   │  │ Git CLI  │  │  Nginx Process           │      │
│  │  PostgreSQL │  │  Server  │  │ (system) │  │  /etc/nginx/gitdeploy.d/ │      │
│  │  Database   │  │ (opt.)   │  │          │  │  app-{id}.conf           │      │
│  └────────────-┘  └──────────┘  └──────────┘  └─────────────────────────┘      │
│            │                         │                     │                     │
│  ┌─────────▼──────────────────────────────────────────────────┐                 │
│  │              Docker Engine                                   │                │
│  │   app_1_container:10000   app_2_container:10001  ...         │                │
│  └──────────────────────────────────────────────────────────────┘                │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    Secret Manager Sidecar Process (:8001)                  │ │
│  │                                                                             │ │
│  │  ┌────────────┐   ┌──────────────┐   ┌──────────────────┐                  │ │
│  │  │  FastAPI   │   │  Fernet      │   │  SQLite          │                  │ │
│  │  │  Router    │──>│  crypto.py   │──>│  secrets.db      │                  │ │
│  │  │  /secrets  │   │  (AES-128 +  │   │  SecretStore     │                  │ │
│  │  │  /admin    │   │   HMAC)      │   │  table           │                  │ │
│  │  └────────────┘   └──────────────┘   └──────────────────┘                  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
         │                                                 │
         │ HTTPS :443 (via Cloudflare Tunnel)              │  DNS *.yourdomain.com
         │                                                 │
┌────────▼─────────────────────────┐             ┌────────▼──────────────────┐
│         Cloudflare Edge           │             │    React Frontend          │
│  *.yourdomain.com                 │             │    (:5173 dev / CDN prod)  │
│  tunnel → Nginx :80               │             │    TanStack Query + Zustand│
└──────────────────────────────────┘             └───────────────────────────┘
```
