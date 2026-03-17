# Layered Architecture — gitDeploy

This document describes the architectural layers of the gitDeploy system, how they interact, and what responsibilities each layer owns.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                          │
│                React Frontend (gitdeploy-ui)                     │
│                                                                  │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│   │  Auth Pages │  │  App Pages   │  │  Admin Dashboard     │  │
│   │  /login     │  │  /dashboard  │  │  /admin              │  │
│   │  /signup    │  │  /apps/new   │  │  Health · Users      │  │
│   └─────────────┘  │  /apps/:id   │  │  Apps · Error Logs   │  │
│                    └──────────────┘  └──────────────────────┘  │
│                                                                  │
│   State: Zustand (auth store)      HTTP Client: Axios            │
│   Auto-refresh: Axios interceptor  Forms: React Hook Form + Zod  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / REST (JSON)
                           │ Authorization: Bearer <access_token>
┌──────────────────────────▼──────────────────────────────────────┐
│                         API LAYER                                │
│                    FastAPI (api/v1/)                              │
│                                                                  │
│   ┌──────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│   │  auth.py     │  │  apps.py    │  │  admin.py            │  │
│   │  /register   │  │  /create    │  │  /health             │  │
│   │  /login      │  │  /list      │  │  /apps (all users)   │  │
│   │  /refresh    │  │  /{id}      │  │  /users              │  │
│   │  /logout     │  │  /deploy    │  │  /errors             │  │
│   │  /me         │  │  /delete    │  │                      │  │
│   └──────────────┘  └─────────────┘  └──────────────────────┘  │
│                                                                  │
│   Input validation: Pydantic schemas                             │
│   Auth dependencies: get_current_user, require_admin             │
│   Error handling: global exception_handler middleware            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Function calls (Python)
                           │ Dependency injection (FastAPI DI)
┌──────────────────────────▼──────────────────────────────────────┐
│                       SERVICE LAYER                              │
│                    (app/services/)                               │
│                                                                  │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐ │
│   │  auth.py   │  │ deploy.py  │  │ docker.py  │  │port_mgr  │ │
│   │            │  │            │  │            │  │.py       │ │
│   │ JWT create │  │ validate   │  │ build img  │  │          │ │
│   │ JWT verify │  │ github url │  │ run ctnr   │  │ OS scan  │ │
│   │ bcrypt     │  │ git clone  │  │ stop/rm    │  │ DB scan  │ │
│   │ hash/check │  │ git pull   │  │ rmi        │  │ find port│ │
│   └────────────┘  └────────────┘  └────────────┘  └──────────┘ │
│                                                                  │
│   ┌───────────────┐  ┌─────────────────────┐                    │
│   │ system_metrics│  │ redis_service.py     │                    │
│   │ .py           │  │                      │                    │
│   │               │  │ namespaced cache     │                    │
│   │ psutil CPU    │  │ graceful fallback    │                    │
│   │ memory, disk  │  │ gitdeploy: prefix    │                    │
│   │ network, ctrs │  │                      │                    │
│   └───────────────┘  └─────────────────────┘                    │
│                                                                  │
│   Business rules live here — NOT in route handlers               │
│   All DB access goes through AsyncSession from Data Layer        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ SQLAlchemy ORM (async)
                           │ AsyncSession.execute()
┌──────────────────────────▼──────────────────────────────────────┐
│                        DATA LAYER                                │
│              SQLAlchemy 2.0 Async ORM                            │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                    Models (app/models/)                   │  │
│   │  users           apps              error_logs             │  │
│   │  ─────────────   ─────────────     ────────────────       │  │
│   │  id              id                id                     │  │
│   │  username        name              error_code             │  │
│   │  email           subdomain         status_code            │  │
│   │  hashed_pw       repo_url          app_id (FK)            │  │
│   │  role            internal_port     context (JSON)         │  │
│   │  billing_type    container_port    created_at             │  │
│   │  created_at      status                                   │  │
│   │  updated_at      env (JSON)                               │  │
│   │                  user_id (FK)                             │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌───────────────────────┐   ┌──────────────────────────────┐  │
│   │  SQLite (default)     │   │  Redis (optional cache)      │  │
│   │  aiosqlite driver     │   │  aioredis driver             │  │
│   │  gitdeploy.db         │   │  namespace: gitdeploy:       │  │
│   └───────────────────────┘   └──────────────────────────────┘  │
│   ┌───────────────────────┐                                      │
│   │  PostgreSQL (prod)    │                                      │
│   │  asyncpg driver       │                                      │
│   └───────────────────────┘                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ subprocess (asyncio.to_thread)
                           │ filesystem I/O
                           │ HTTP (httpx async)
┌──────────────────────────▼──────────────────────────────────────┐
│                   INFRASTRUCTURE LAYER                           │
│                                                                  │
│   ┌──────────────┐  ┌──────────┐  ┌────────────┐  ┌─────────┐  │
│   │ Docker Engine│  │   Git    │  │   Nginx    │  │Cloudflare│  │
│   │              │  │          │  │            │  │ Tunnel   │  │
│   │ build image  │  │  clone   │  │ subdomain  │  │          │  │
│   │ run ctnr     │  │  pull    │  │ routing    │  │ no open  │  │
│   │ stop/rm/rmi  │  │          │  │ :80 proxy  │  │ ports    │  │
│   │ labels       │  │  GitHub  │  │ per-app    │  │ wildcard │  │
│   └──────────────┘  └──────────┘  │ configs    │  │ *.domain │  │
│                                   └────────────┘  └─────────┘  │
│   ┌─────────────────────────────┐  ┌──────────────────────────┐ │
│   │  Secret Sidecar (port 8001) │  │  psutil (host metrics)   │ │
│   │                             │  │                          │ │
│   │  FastAPI companion service  │  │  CPU, memory, disk,      │ │
│   │  Fernet AES encryption      │  │  network I/O             │ │
│   │  secrets.db (SQLite)        │  │                          │ │
│   │  X-Api-Key authentication   │  └──────────────────────────┘ │
│   └─────────────────────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer Responsibilities

### Presentation Layer

**What it owns:**
- User interface rendering (React components, pages, layouts)
- Client-side form validation (Zod schemas)
- Authentication state management (Zustand store — access token in memory only)
- Silent token refresh logic (Axios response interceptor)
- Route protection (ProtectedRoute component redirects unauthenticated users)
- Loading states, error toasts, status badges

**What it does NOT own:**
- Business logic (no deployment decisions made in the UI)
- Data persistence (no localStorage for tokens)
- Direct infrastructure access

**Communication:** HTTP REST to the API Layer over HTTPS. All requests include `Authorization: Bearer <access_token>` where required.

---

### API Layer

**What it owns:**
- HTTP request routing (FastAPI route definitions)
- Input deserialization and validation (Pydantic schemas)
- Authentication enforcement (dependency injection: `get_current_user`, `require_admin`)
- HTTP response serialisation
- CORS configuration

**What it does NOT own:**
- Business logic (route handlers call service functions, they don't implement logic)
- Database queries (delegated to the Service Layer which uses the Data Layer)
- Infrastructure operations (no Docker/Git calls in route handlers)

**Communication:** Function calls into the Service Layer; yields `AsyncSession` to service functions via dependency injection.

---

### Service Layer

**What it owns:**
- All business logic and orchestration
- Multi-step workflows (e.g., the 10-step deployment pipeline)
- Decision-making (which port to allocate, when to rebuild vs pull, when to fail)
- External service communication: git commands, Docker commands, sidecar HTTP calls
- Error raising (`AppError` subclasses with structured context)

**What it does NOT own:**
- HTTP specifics (services don't know about HTTP status codes — they raise typed exceptions)
- Database schema (services use ORM models, not raw SQL)

**Communication:** Receives `AsyncSession` from the API layer; calls ORM models; issues subprocess commands via `asyncio.to_thread()`; makes HTTP requests to the sidecar via `httpx`.

---

### Data Layer

**What it owns:**
- ORM model definitions (SQLAlchemy declarative models)
- Async database engine configuration
- Session factory (`async_sessionmaker`)
- Redis service wrapper (namespaced cache with graceful fallback)

**What it does NOT own:**
- Query logic (queries are constructed in the Service Layer using the session)
- Schema migration (managed separately by Alembic)

**Communication:** `AsyncSession` passed into service functions; Redis `aioredis` client for cache operations.

---

### Infrastructure Layer

**What it owns:**
- Container runtime (Docker Engine)
- Source code retrieval (Git / GitHub)
- HTTP routing (Nginx)
- Public access (Cloudflare Tunnel)
- Host metrics (psutil)
- Encrypted secret storage (Sidecar)

**What it does NOT own:**
- gitDeploy application logic
- User data or authentication

**Communication:** Receives instructions from the Service Layer via subprocess, filesystem writes, or HTTP. Returns results via exit codes, stdout/stderr, or HTTP responses.

---

## Data Flow Between Layers

```
User Action: "Deploy App"
      │
      ▼ HTTP POST /api/v1/apps/{id}/deploy
  [API LAYER]
  - Validate request body (Pydantic)
  - Check auth token (dependency)
  - Call DeployService.deploy_app(db, app, overrides)
      │
      ▼ Function call + AsyncSession
  [SERVICE LAYER]
  - DeployService orchestrates 10 sub-steps
  - Each sub-step uses other services (DockerService, PortManager, etc.)
      │
      ├──▼ SELECT app from DB (via AsyncSession)
      │  [DATA LAYER: SQLAlchemy ORM → SQLite/PostgreSQL]
      │
      ├──▼ git clone (subprocess via asyncio.to_thread)
      │  [INFRASTRUCTURE LAYER: Git → GitHub]
      │
      ├──▼ find_free_port (psutil + DB query)
      │  [INFRASTRUCTURE LAYER: psutil]
      │  [DATA LAYER: SELECT internal_port FROM apps]
      │
      ├──▼ docker build (subprocess via asyncio.to_thread)
      │  [INFRASTRUCTURE LAYER: Docker Engine]
      │
      ├──▼ GET /secrets/{app_id} (httpx async)
      │  [INFRASTRUCTURE LAYER: Sidecar]
      │
      ├──▼ docker run (subprocess via asyncio.to_thread)
      │  [INFRASTRUCTURE LAYER: Docker Engine]
      │
      ├──▼ UPDATE apps SET status='running' (via AsyncSession)
      │  [DATA LAYER: SQLAlchemy ORM → SQLite/PostgreSQL]
      │
      └──▼ write Nginx config + reload
         [INFRASTRUCTURE LAYER: Nginx]
      │
      ▼ Return {id, status: "running"}
  [API LAYER]
  - Serialize response (Pydantic)
  - Return HTTP 201
      │
      ▼ HTTP 201 JSON response
  [PRESENTATION LAYER]
  - Update UI, show toast, refresh status badge
```

---

## Async Architecture

All layers are fully asynchronous:

| Layer | Async Mechanism |
|-------|----------------|
| API Layer | FastAPI `async def` route handlers |
| Service Layer | `async def` service methods; `asyncio.to_thread()` for blocking subprocess calls |
| Data Layer | `AsyncSession`, `async_sessionmaker`, `await session.execute()` |
| Redis | `aioredis` async client |
| Sidecar HTTP | `httpx.AsyncClient` |
| Infrastructure | Subprocess calls offloaded to thread pool |

This design means the single Uvicorn event loop can handle many concurrent requests even while a Docker build (which may take 60+ seconds) is running for one user. The blocking subprocess runs in a thread, not on the event loop.

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Business logic in Service Layer, not route handlers | Keeps routes thin and testable; logic can be reused across endpoints |
| `asyncio.to_thread()` for subprocess | Docker build/run and git clone are blocking C library calls. Running them on the event loop would block all other requests. |
| Pydantic for input validation | Single source of truth for schemas; auto-generates API docs; validation errors are automatically HTTP 422 |
| Error codes in numeric ranges | Makes error classification machine-readable; enables DB-level filtering without string parsing |
| Sidecar pattern for secrets | Separates secret storage concerns from app lifecycle; the sidecar can be replaced or upgraded independently |
| `REDIS_ENABLED` flag with no-op fallback | Allows the system to run in environments without Redis; caching is an optimisation, not a requirement |
| SQLite default, PostgreSQL upgrade path | Lowers barrier to entry; single URL change to switch backends |
