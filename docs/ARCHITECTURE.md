# Architecture — gitDeploy

This document describes the layered architecture of gitDeploy, the responsibilities of each layer, how layers communicate, and the deployment topology.

---

## 1. Architectural Overview

gitDeploy follows a classic layered architecture with five distinct layers. Each layer depends only on the layer directly below it; no layer reaches upward. The only exception is the error system, which is cross-cutting and can be raised from any layer.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                         Layer 5 — Presentation                                  │
│  React 19 / Vite / TypeScript                                                   │
│  TanStack Query v5  ·  Zustand  ·  React Router v7  ·  Tailwind CSS / shadcn/ui │
│  axios  ·  JWT in memory  ·  refresh cookie (HttpOnly)                          │
└────────────────────────────────────────────────────────────────────────────────┘
                             ↕  HTTP / JSON  (port 5173 dev, CDN prod)
┌────────────────────────────────────────────────────────────────────────────────┐
│                         Layer 4 — API / Route Layer                              │
│  FastAPI 0.123  ·  Uvicorn  ·  Starlette CORS middleware                        │
│  api/v1/auth.py     — /api/v1/auth/*                                            │
│  api/v1/apps.py     — /api/v1/apps/*                                            │
│  api/v1/admin.py    — /api/v1/admin/*                                           │
│  Pydantic v2 schemas (request validation + response serialisation)              │
│  JWT Bearer token extraction  ·  Dependency injection (get_db, get_current_user)│
└────────────────────────────────────────────────────────────────────────────────┘
                             ↕  Python function calls
┌────────────────────────────────────────────────────────────────────────────────┐
│                         Layer 3 — Service Layer                                  │
│  app/services/auth.py         — JWT sign/verify, bcrypt, user lookup            │
│  app/services/deploy.py       — GitHub validation, git clone/pull/branch        │
│  app/services/docker.py       — docker build / run / rm (CLI subprocess)        │
│  app/services/docker_command_builder.py — fluent builder for Docker CLI args    │
│  app/services/port_manager.py — async port allocator (DB + OS socket check)    │
│  app/services/nginx_manager.py — per-app Nginx config write/remove/reload      │
│  app/services/redis_service.py — async Redis wrapper (gitdeploy: namespace)    │
│  app/services/system_metrics.py — psutil CPU/mem/disk/net collection           │
│  app/Errors/                  — custom AppBaseError hierarchy + DB logger       │
└────────────────────────────────────────────────────────────────────────────────┘
                             ↕  Python function calls / SQLAlchemy ORM
┌────────────────────────────────────────────────────────────────────────────────┐
│                         Layer 2 — Data Layer                                     │
│  SQLAlchemy 2.0 async (create_async_engine, AsyncSession, async_sessionmaker)   │
│  aiosqlite driver (SQLite default)  ·  asyncpg driver (PostgreSQL optional)     │
│  app/models/users.py       — Users ORM model                                    │
│  app/models/app_model.py   — AppModel ORM model                                 │
│  app/models/error_log.py   — ErrorLog ORM model                                 │
│  Alembic migrations (schema version management)                                  │
│  Redis (optional, async, gitdeploy: namespace)                                   │
└────────────────────────────────────────────────────────────────────────────────┘
                             ↕  OS subprocess / socket / filesystem calls
┌────────────────────────────────────────────────────────────────────────────────┐
│                         Layer 1 — Infrastructure Layer                           │
│  Docker Engine   — build images, run containers, resource limits                │
│  Git CLI         — clone/pull public GitHub repositories                        │
│  Nginx           — per-app reverse proxy (optional, auto-configured)            │
│  Cloudflare Tunnel — public HTTPS routing without open inbound ports (optional) │
│  SQLite / PostgreSQL database files                                              │
│  /opt/apps/{id}  — cloned source code directories                               │
│  /opt/logs/{id}  — container log directories                                    │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Descriptions

### Layer 5 — Presentation

The React 19 frontend is a single-page application. It communicates exclusively with the gitDeploy API; it has no direct connection to Docker, Nginx, or the database.

Key design decisions:
- **TanStack Query** manages server state: caching API responses, background refetching, and cache invalidation on mutations.
- **Zustand** holds client-only UI state (auth token in memory, UI flags).
- **Access tokens are never written to `localStorage` or `sessionStorage`** — they are held in Zustand store (JavaScript memory) to mitigate XSS token theft. The refresh token lives only in an HttpOnly cookie.
- API calls use axios interceptors to automatically call `POST /refresh` when a 401 is received, then retry the original request.

### Layer 4 — API / Route Layer

FastAPI handles HTTP routing, request parsing, and response serialisation. Each router module is thin: it validates input using Pydantic schemas, delegates business logic to the service layer, and formats the response.

The route layer is responsible for:
- Deserialising and validating incoming JSON via Pydantic v2 models
- Injecting dependencies (`AsyncSession`, `Users`) via FastAPI's `Depends()` mechanism
- Enforcing ownership (`_get_owned_app`) and role checks (`get_admin_user`)
- Returning appropriate HTTP status codes
- Never containing business logic — all substantive operations are in the service layer

### Layer 3 — Service Layer

The service layer contains all business logic. Each service is a collection of pure functions (no class state), which makes them easy to unit test.

Key principles:
- **Blocking operations are always wrapped in `asyncio.to_thread`** — this includes Git subprocess calls, Docker subprocess calls, and psutil system calls
- **Services raise `AppBaseError` subclasses**, never HTTPException — the HTTP mapping is in the exception handler
- **Services are not aware of FastAPI** — they accept and return plain Python objects, not Request/Response objects

### Layer 2 — Data Layer

SQLAlchemy 2.0 async provides the ORM and connection pool. The `get_db` dependency yields an `AsyncSession` per request and closes it after the response.

The `TimeStatusMixin` adds `created_at` and `updated_at` columns to `Users` and `AppModel` tables without repetition.

Redis (when enabled) acts as a read-through cache. All Redis operations are fire-and-forget: a miss or error causes a transparent fallback to the database.

### Layer 1 — Infrastructure Layer

The infrastructure layer consists of external processes and the filesystem. The service layer interacts with it exclusively through:
- `subprocess.run` / `subprocess.Popen` for Docker and Git
- `socket.socket.bind()` for port availability checks
- `pathlib.Path` for filesystem operations
- `asyncio.to_thread` to wrap all of the above

---

## 3. Cross-Cutting Concerns

### Error System

The error system cuts across all layers. Any layer can raise an `AppBaseError` subclass. The exception handler in `app/Errors/exception_handler.py` intercepts it at the API layer, logs it to the database, and returns a structured JSON response.

```
AppBaseError subclasses (raised in service layer)
        ↓
app_error_handler (registered in main.py)
        ↓
error_logger.log_error(error, db)  →  INSERT error_logs
        ↓
JSONResponse({error_code, status_code, message})
```

### Configuration

`app/config.py` reads all configuration from environment variables at import time. No other module reads from the environment directly — all config flows through the `Config` class. This ensures that changing a setting requires changing only one environment variable, and makes the entire config surface visible in one file.

### Logging

Standard Python `logging` is configured in `main.py` with a common format. Every module uses `logging.getLogger(__name__)` so log messages carry the module path, enabling targeted filtering.

---

## 4. Sidecar Architecture

The Secret Manager Sidecar is architecturally separate from the main API. It mirrors the main API's layered structure but is a fully independent process:

```
┌────────────────────────────────────────────────────┐
│         Secret Manager Sidecar (:8001)              │
│                                                     │
│  Route Layer   — sidecar/main.py  (FastAPI)         │
│  Crypto Layer  — sidecar/crypto.py (Fernet)         │
│  Data Layer    — sidecar/database.py (async SQLite) │
│  Model         — sidecar/models.py (SecretStore)    │
│  Config        — sidecar/config.py                  │
│  Auth          — sidecar/dependencies.py (API key)  │
└────────────────────────────────────────────────────┘
         ↕  HTTP (X-Api-Key auth)
┌────────────────────────────────────────────────────┐
│                gitDeploy Main API                   │
│  (references SIDECAR_URL and SIDECAR_API_KEY from   │
│   Config — no code is shared between the two)       │
└────────────────────────────────────────────────────┘
```

Benefits of this separation:
- The sidecar's database (`secrets.db`) never shares a file handle with the main API's database.
- The encryption key (`SIDECAR_ENCRYPTION_KEY`) is never loaded into the main API process.
- The sidecar can be replaced or upgraded independently.
- A compromised main API does not automatically expose the encryption key.

---

## 5. Deployment Topology

### Minimal (development / single user)

```
Developer machine
├── gitDeploy API :8000   (uvicorn, single worker, SQLite)
├── React dev server :5173
└── Docker Engine
    └── app_N_container :10000-65535
```

No Nginx, no Cloudflare, no Redis. Apps are accessible on `localhost:{internal_port}`.

### Single server (LAN / homelab)

```
Linux server (Ubuntu)
├── Nginx :80
│   └── includes /etc/nginx/gitdeploy.d/*.conf
│       (written by gitDeploy on each deploy)
├── gitDeploy API :8000   (uvicorn or systemd service)
│   └── SQLite: /var/lib/gitdeploy/gitdeploy.db
├── Secret Sidecar :8001  (separate uvicorn or systemd service)
│   └── SQLite: /var/lib/gitdeploy/secrets.db
└── Docker Engine
    ├── app_1_container :10000
    ├── app_2_container :10001
    └── ...
```

DNS: `*.yourdomain.local → server_ip` (local DNS or `/etc/hosts`).

### Production (public internet, Cloudflare)

```
                    Cloudflare Edge
                         |
              Cloudflare Tunnel (outbound only)
                         |
              cloudflared daemon (host)
                         |
              Nginx :80 (reverse proxy)
              includes /etc/nginx/gitdeploy.d/*.conf
                         |
              ┌──────────┴──────────────────────────────┐
              │          Linux server                    │
              │                                         │
              │  gitDeploy API :8000                    │
              │    PostgreSQL database                  │
              │    Redis :6379 (optional)               │
              │                                         │
              │  Secret Sidecar :8001                   │
              │    SQLite: secrets.db (restricted 600)  │
              │                                         │
              │  Docker Engine                          │
              │    app_N_container :10000+              │
              └─────────────────────────────────────────┘
```

DNS: Cloudflare manages `*.yourdomain.com` → tunnel CNAME. No inbound ports need to be opened on the server firewall.

### High-availability considerations (future)

The current architecture is single-server. For HA:
- PostgreSQL must be used (SQLite does not support concurrent writers).
- Redis must be used for shared cache across workers.
- `JWT_SECRET` must be a stable, shared value (not auto-generated) across all instances.
- The sidecar must run as a single instance (SQLite write concurrency limitation) or be migrated to PostgreSQL.
- A shared filesystem (NFS or S3-backed) is needed for `/opt/apps` and `/opt/logs`.
- A load balancer (HAProxy, Nginx upstream, or Cloudflare Load Balancing) distributes API traffic.

---

## 6. Request Lifecycle

A typical authenticated request flows through the layers as follows:

```
HTTP Request arrives at Uvicorn
    ↓
CORS middleware (Starlette) — check Origin header
    ↓
FastAPI Router — match path to handler function
    ↓
Dependency injection:
  1. get_db()          → yield AsyncSession from pool
  2. get_current_user() → decode Bearer token → SELECT user
    ↓
Handler function (api layer):
  3. Deserialise request body via Pydantic model
  4. Validate domain rules (ownership, status)
  5. Call service layer functions
    ↓
Service layer:
  6. Business logic (git, docker, port, nginx, redis)
  7. Raise AppBaseError on failure
    ↓
Data layer:
  8. SELECT / INSERT / UPDATE / DELETE via SQLAlchemy async
  9. db.commit() or db.rollback()
    ↓
Handler returns response dict/model
    ↓
FastAPI serialises to JSON via Pydantic response_model
    ↓
HTTP Response sent by Uvicorn

Parallel: if AppBaseError raised at any point →
  exception_handler.py:
    - log to error_logs table
    - return JSONResponse with error JSON
```
