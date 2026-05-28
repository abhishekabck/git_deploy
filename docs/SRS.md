# Software Requirements Specification — gitDeploy v2
**Self-Hosted Automated Deployment Platform**
Version: 2.0 | Date: 2026-04-29 | Status: Planning (Rebuild from scratch)

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Goals & Scope](#2-goals--scope)
3. [Stakeholders & User Roles](#3-stakeholders--user-roles)
4. [Functional Requirements](#4-functional-requirements)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [System Architecture Overview](#6-system-architecture-overview)
7. [Directory Structure](#7-directory-structure)
8. [Database Design](#8-database-design)
9. [API Design](#9-api-design)
10. [WebSocket Design](#10-websocket-design)
11. [Deployment Pipeline Design](#11-deployment-pipeline-design)
12. [Logging System Design](#12-logging-system-design)
13. [Subdomain Management](#13-subdomain-management)
14. [Security Design](#14-security-design)
15. [Tech Stack Decisions](#15-tech-stack-decisions)
16. [Glossary](#16-glossary)

---

## 1. Project Overview

gitDeploy is a **self-hosted PaaS (Platform as a Service)** that automates the complete deployment lifecycle of GitHub repositories. It provisions Docker containers, allocates ports, configures Nginx reverse proxy, and exposes each deployed application at a unique subdomain — all triggered by a single API call.

**Live at:** gitdeploy.online

### What It Solves
Developers waste hours on repetitive deploy scripts, SSH sessions, and Nginx config edits.
gitDeploy collapses that into: _push to GitHub → call API → app is live at {subdomain}.gitdeploy.online_.

### v2 New Additions
- Per-app **container resource monitoring** (CPU, memory, network) — not just host-level.
- **User-defined subdomains** with real-time availability checking.
- **Structured dual-DB logging** — PostgreSQL for pipeline audit + MongoDB for raw container logs.
- **Celery task queue** replacing inline subprocess calls (survives server restarts).
- Correlation ID logging and JSON-structured application logs.

---

## 2. Goals & Scope

### In Scope
- User registration, authentication (JWT + refresh tokens), email OTP verification.
- App lifecycle: create → deploy → monitor → restart → stop → delete.
- Real-time WebSocket log streaming (container stdout/stderr during deploy and runtime).
- Real-time system and per-container resource metrics pushed via WebSocket.
- Nginx reverse proxy auto-configuration per app.
- Custom subdomain selection with uniqueness + format enforcement.
- Structured application logging (internal audit/event logs).
- Admin panel: manage users, view all apps, force-stop containers.

### Out of Scope (v2)
- Multi-node / Kubernetes orchestration.
- Private GitHub repo support (OAuth token flow).
- Billing / payment processing.
- Custom domain (BYOD — bring your own domain) support.

---

## 3. Stakeholders & User Roles

| Role | Description | Access |
|------|-------------|--------|
| `ADMIN` | Platform operator | All users, all apps, system metrics, force ops |
| `USER` | Developer using the platform | Own apps only, own metrics, subdomain selection |

**Billing Types (quota gate — implement later):**

| Type | Limit |
|------|-------|
| `FREE` | 2 apps max |
| `PAID` | Unlimited apps |

---

## 4. Functional Requirements

### 4.1 Authentication & User Management
- **FR-AUTH-01** User registers with username, email, password.
- **FR-AUTH-02** Email OTP verification required before first login.
- **FR-AUTH-03** Login returns short-lived access token (15 min) + long-lived refresh token (7 days).
- **FR-AUTH-04** Refresh endpoint issues a new access token using the refresh token.
- **FR-AUTH-05** Password reset via email OTP flow.
- **FR-AUTH-06** Logout blacklists the current refresh token.
- **FR-AUTH-07** Admin can disable/enable any user account.

### 4.2 App Management
- **FR-APP-01** User creates an app by providing: name, GitHub repo URL, branch, container port, Dockerfile path, source directory, environment variables.
- **FR-APP-02** App gets a unique subdomain. Default: `app-{id}`. User may choose custom (§4.5).
- **FR-APP-03** User triggers a deploy (clone/pull → build → run pipeline).
- **FR-APP-04** User can restart a running app (stop container → re-run same image).
- **FR-APP-05** User can stop a running app (status → STOPPED).
- **FR-APP-06** User can delete an app: stop container, remove Docker image, remove Nginx conf, delete source files.
- **FR-APP-07** App list supports pagination and status-based filtering.
- **FR-APP-08** App detail returns: status, subdomain URL, env var keys (values masked), timestamps.

### 4.3 Deployment Pipeline
- **FR-DEPLOY-01** Validate GitHub repo URL is public and reachable (GitHub API check) before any git operation.
- **FR-DEPLOY-02** Clone repo if not present; pull latest if already cloned.
- **FR-DEPLOY-03** Check out the specified branch.
- **FR-DEPLOY-04** Build Docker image from specified Dockerfile and build path.
- **FR-DEPLOY-05** Allocate a free internal port (10000–65535) using DB lock + OS socket verification.
- **FR-DEPLOY-06** Run the container with the allocated port, passing env vars.
- **FR-DEPLOY-07** Write Nginx config for `{subdomain}.gitdeploy.online → 127.0.0.1:{port}` and hot-reload Nginx.
- **FR-DEPLOY-08** Each pipeline step streams stdout/stderr in real time via WebSocket.
- **FR-DEPLOY-09** Pipeline failures update app status to `ERROR` and record the failing step + reason.

### 4.4 Real-Time Monitoring
- **FR-MON-01** Host-level metrics (CPU %, memory %, disk %, network I/O) pushed via WebSocket every 5s.
- **FR-MON-02** Per-container metrics (CPU %, memory %, network I/O) pushed per app via WebSocket. Source: `docker stats --no-stream`.
- **FR-MON-03** Container metrics snapshotted to MongoDB every 60s by a Celery beat task for historical charts.

### 4.5 Subdomain Management
- **FR-SUB-01** Default subdomain assigned at app creation: `app-{id}`.
- **FR-SUB-02** User can check availability of a custom subdomain before committing.
- **FR-SUB-03** User can change subdomain only if: app is NOT RUNNING, and the name is not taken.
- **FR-SUB-04** On subdomain change: remove old Nginx conf, write new one, hot-reload Nginx.
- **FR-SUB-05** Subdomain validation: lowercase alphanumeric + hyphens, 3–63 chars, no leading/trailing hyphens.

### 4.6 Logging System
- **FR-LOG-01** All API requests logged with: timestamp, user_id, endpoint, method, status_code, duration_ms, request_id.
- **FR-LOG-02** Deployment pipeline steps logged as rows in PostgreSQL `deployment_logs` (step, status, message, duration_ms).
- **FR-LOG-03** Container stdout/stderr stored in MongoDB (one document per line: app_id, timestamp, stream, message).
- **FR-LOG-04** User can query deployment history: list of deploy runs with step-by-step breakdown.
- **FR-LOG-05** User can query container log history with time-range filters and cursor pagination.
- **FR-LOG-06** Logs older than retention period (default: 30 days) auto-purged via MongoDB TTL index.

### 4.7 Admin Features
- **FR-ADMIN-01** List all users with app count and account status.
- **FR-ADMIN-02** List all apps across all users.
- **FR-ADMIN-03** Force-stop any running container.
- **FR-ADMIN-04** View system-wide resource metrics.

---

## 5. Non-Functional Requirements

### 5.1 Performance
- **NFR-PERF-01** Read endpoint response: < 200ms P95 under 100 concurrent users.
- **NFR-PERF-02** Deploy trigger (before async hand-off to Celery): < 500ms.
- **NFR-PERF-03** WebSocket metric push latency: < 1s from collection to browser.
- **NFR-PERF-04** Port allocation: < 50ms for up to 1,000 registered apps.

### 5.2 Scalability
- **NFR-SCALE-01** API layer is stateless — any shared state lives in Redis/DB. Multiple API instances can run behind a load balancer without session stickiness.
- **NFR-SCALE-02** Celery workers scale independently of API workers (add more worker processes without changing API).
- **NFR-SCALE-03** Database connection pooling via asyncpg (configurable pool size).
- **NFR-SCALE-04** Port allocation uses `SELECT FOR UPDATE SKIP LOCKED` preventing race conditions under concurrent multi-tenant deployments.

### 5.3 Reliability
- **NFR-REL-01** Nginx reload failure → app.status = ERROR, container still runs, reason logged.
- **NFR-REL-02** Deploy step failure → automatic cleanup: partial containers stopped, ports released.
- **NFR-REL-03** On startup, reconcile app statuses against actual Docker container states.
- **NFR-REL-04** Celery tasks: 3 retries with exponential backoff for transient failures.

### 5.4 Security
- **NFR-SEC-01** JWT secrets from environment only — never hardcoded.
- **NFR-SEC-02** Passwords stored as bcrypt hashes (cost factor ≥ 12).
- **NFR-SEC-03** Env var values never returned by API — keys only shown in responses.
- **NFR-SEC-04** Auth endpoints rate-limited (login, register, OTP verify).
- **NFR-SEC-05** Subdomain server-side validated with regex — no shell injection via nginx template.
- **NFR-SEC-06** Repo URL validated against GitHub API before any git clone operation (prevents SSRF).

### 5.5 Observability
- **NFR-OBS-01** Structured JSON logs: `{ timestamp, level, logger, request_id, user_id, message }`.
- **NFR-OBS-02** `request_id` (UUID) generated per HTTP request by middleware, stored in `contextvars.ContextVar` so all log calls in that request automatically include it.
- **NFR-OBS-03** `GET /health` returns DB + Redis + MongoDB connectivity status.

### 5.6 Maintainability
- **NFR-MAINT-01** All schema changes via Alembic migrations only — no `Base.metadata.create_all` in production.
- **NFR-MAINT-02** API versioned under `/api/v1/` — future breaking changes go to `/api/v2/`.
- **NFR-MAINT-03** `services/` layer has zero FastAPI imports — callable from CLI, tests, and Celery tasks equally.
- **NFR-MAINT-04** All configuration in `core/config.py` using Pydantic `BaseSettings`.

---

## 6. System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                             │
│     React Dashboard (Vite + TypeScript)  │  REST Consumers       │
└───────────────────────┬──────────────────────────────────────────┘
                        │ HTTPS / WSS
┌───────────────────────▼──────────────────────────────────────────┐
│                        NGINX                                     │
│  gitdeploy.online → FastAPI  │  app-{x}.gitdeploy.online → Docker│
└───────────────────────┬──────────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────────────┐
│                     FASTAPI APPLICATION                          │
│                                                                  │
│   Middleware: RequestID | AccessLog | RateLimit | CORS | Auth    │
│                                                                  │
│   ┌────────────────┐    ┌──────────────────┐                    │
│   │  REST /api/v1  │    │  WebSocket /ws/* │                    │
│   └───────┬────────┘    └────────┬─────────┘                    │
│           └──────────┬───────────┘                              │
│                      │ calls                                     │
│   ┌──────────────────▼───────────────────────────────────────┐  │
│   │                    Service Layer                         │  │
│   │  AuthSvc │ AppSvc │ DeploySvc │ NginxSvc │ MetricsSvc   │  │
│   └──────────────────┬───────────────────────────────────────┘  │
│                      │ enqueues                                  │
└──────────────────────┼───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                    CELERY WORKERS                                │
│   clone_task │ build_task │ run_task │ log_tail │ purge (beat)  │
└──────────────────────┬───────────────────────────────────────────┘
                       │ reads/writes
┌──────────────────────▼───────────────────────────────────────────┐
│                    INFRASTRUCTURE                                │
│  PostgreSQL (users, apps, deploy_logs)                           │
│  MongoDB    (container_logs, container_metrics snapshots)        │
│  Redis      (broker + pub/sub + cache + blacklist)               │
│  Docker Engine                                                   │
│  Nginx (reverse proxy)                                           │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibility Map

| Component | Job |
|-----------|-----|
| FastAPI | HTTP/WebSocket server, routing, auth enforcement |
| Celery | Async deploy pipeline, log tailing, scheduled maintenance |
| Redis | Celery broker, WebSocket pub/sub fan-out, token blacklist, rate limiting |
| PostgreSQL | Users, apps, deployment step logs (relational, ACID) |
| MongoDB | Container log lines, container metric snapshots (time-series, TTL) |
| Nginx | Reverse proxy for API + per-app routing, TLS |
| Docker | Container lifecycle |

---

## 7. Directory Structure

This is the target layout you will build. Every folder is a deliberate boundary.

```
gitDeploy/                              ← project root (git repo)
│
├── backend/                            ← FastAPI app root
│   ├── main.py                         ← create_app(), lifespan(), register routers + middleware
│   ├── alembic.ini
│   │
│   ├── core/                           ← Framework plumbing. ZERO business logic here.
│   │   ├── config.py                   ← Pydantic BaseSettings — every env var typed and documented
│   │   ├── database.py                 ← SQLAlchemy async engine, AsyncSession factory
│   │   ├── mongo.py                    ← Motor client + collection accessors (container_logs, metrics)
│   │   ├── redis_client.py             ← aioredis connection pool
│   │   ├── security.py                 ← jwt_encode, jwt_decode, bcrypt_hash, bcrypt_verify
│   │   ├── logging.py                  ← JSON formatter, request_id ContextVar, get_logger()
│   │   ├── middleware.py               ← RequestIDMiddleware, AccessLogMiddleware
│   │   └── dependencies.py             ← Depends() factories: get_db, get_mongo, get_current_user, require_admin
│   │
│   ├── api/
│   │   ├── __init__.py                 ← single APIRouter aggregating all v1 routers
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py                 ← /register /login /refresh /verify-otp /forgot-password /logout
│   │       ├── apps.py                 ← CRUD + /deploy /restart /stop
│   │       ├── subdomains.py           ← /subdomains/check  PATCH /apps/{id}/subdomain
│   │       ├── logs.py                 ← /apps/{id}/deployments  /apps/{id}/logs
│   │       ├── metrics.py              ← /metrics/host  /apps/{id}/metrics  /apps/{id}/metrics/history
│   │       ├── websocket.py            ← /ws/metrics/host  /ws/apps/{id}/metrics  /ws/apps/{id}/logs
│   │       └── admin.py                ← /admin/* (role guard on entire router)
│   │
│   ├── models/                         ← SQLAlchemy ORM models only — no query logic
│   │   ├── __init__.py
│   │   ├── mixins.py                   ← TimestampMixin (created_at, updated_at auto-set)
│   │   ├── user.py
│   │   ├── app.py
│   │   └── deployment_log.py           ← one row per pipeline step per deploy
│   │
│   ├── schemas/                        ← Pydantic v2 models for request validation + response shaping
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── app.py
│   │   ├── subdomain.py
│   │   ├── logs.py
│   │   └── metrics.py
│   │
│   ├── services/                       ← Business logic. `import fastapi` is BANNED here.
│   │   ├── __init__.py
│   │   ├── auth_service.py             ← register, login, OTP, token management
│   │   ├── app_service.py              ← app CRUD, subdomain change logic
│   │   ├── deploy_service.py           ← orchestrates pipeline steps, calls workers
│   │   ├── git_service.py              ← validate_repo, clone, pull, checkout_branch
│   │   ├── docker_service.py           ← build, run, stop, remove, get_stats
│   │   ├── port_manager.py             ← allocate_port (DB lock + socket verify)
│   │   ├── nginx_service.py            ← write_conf, remove_conf, reload
│   │   ├── metrics_service.py          ← host_metrics (psutil) + container_metrics (docker stats)
│   │   ├── log_service.py              ← write/query deploy_logs (PG) + container_logs (Mongo)
│   │   └── otp_service.py              ← generate, store in Redis, verify OTP
│   │
│   ├── workers/                        ← Celery tasks. Thin wrappers over services/. No logic here.
│   │   ├── __init__.py
│   │   ├── celery_app.py               ← Celery instance, Redis broker config, Beat schedule
│   │   ├── deploy_tasks.py             ← chain: clone_task | build_task | run_task | nginx_task
│   │   ├── cleanup_tasks.py            ← remove_container_task, remove_image_task, release_port_task
│   │   └── maintenance_tasks.py        ← purge_old_logs_task (beat: daily), snapshot_metrics_task (beat: 60s)
│   │
│   ├── errors/
│   │   ├── __init__.py
│   │   ├── exceptions.py               ← All custom errors: AppNotFoundError, PortExhaustedError, etc.
│   │   └── handlers.py                 ← register_handlers(app) called from main.py
│   │
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   │
│   └── tests/
│       ├── conftest.py                 ← Fixtures: test DB, async test client, fake user factory
│       ├── test_auth.py
│       ├── test_apps.py
│       ├── test_deploy.py
│       └── test_subdomains.py
│
├── frontend/                           ← React app (Vite + TypeScript)
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                        ← Axios instances + typed API call functions
│       │   ├── client.ts               ← base Axios, interceptors (attach token, handle 401 → refresh)
│       │   ├── auth.ts
│       │   ├── apps.ts
│       │   └── metrics.ts
│       ├── components/
│       │   ├── AppCard.tsx
│       │   ├── LogViewer.tsx           ← Virtualized scrollable log panel (react-virtual)
│       │   ├── MetricsChart.tsx        ← Recharts line chart for CPU/memory history
│       │   └── StatusBadge.tsx
│       ├── pages/
│       │   ├── Login.tsx
│       │   ├── Dashboard.tsx
│       │   ├── AppDetail.tsx
│       │   └── Admin.tsx
│       ├── hooks/
│       │   ├── useWebSocket.ts         ← generic WS hook: connect, parse, auto-reconnect on close
│       │   ├── useMetrics.ts
│       │   └── useDeployLogs.ts
│       └── store/
│           ├── authStore.ts            ← Zustand: token, user
│           └── appStore.ts             ← Zustand: app list, selected app
│
├── sidecar/                            ← Separate privileged agent (optional)
│   ├── main.py
│   ├── config.py
│   └── crypto.py
│
├── nginx/
│   ├── gitdeploy.conf                  ← Main nginx config (includes gitdeploy.d/*.conf)
│   └── gitdeploy.d/                    ← Per-app configs, auto-managed by nginx_service.py
│
├── scripts/
│   ├── setup_nginx.sh
│   ├── setup_postgres.sh
│   └── setup_mongo.sh
│
├── docs/
│   ├── SRS.md                          ← This file
│   └── ARCHITECTURE_IMPROVEMENTS.md
│
├── docker-compose.yml                  ← Dev: api + celery + postgres + mongo + redis
├── .env.example
├── .gitignore
└── README.md
```

### The Four Rules for Structural Discipline
1. **`core/`** — framework wiring only. If it touches business logic, it belongs in `services/`.
2. **`services/`** — pure Python functions. `from fastapi import ...` is a linting error in this folder.
3. **`workers/`** — Celery tasks call exactly one `services/` function. No logic in task bodies.
4. **`api/`** routes — three lines: validate → call service → return schema. DB queries belong in services, not routes.

---

## 8. Database Design

### 8.1 PostgreSQL (Source of truth — relational, ACID)

**users**
```sql
id              SERIAL PRIMARY KEY
username        VARCHAR(50) UNIQUE NOT NULL
email           VARCHAR(255) UNIQUE NOT NULL
hashed_password VARCHAR NOT NULL
role            ENUM('user','admin') DEFAULT 'user'
billing_type    ENUM('free','paid') DEFAULT 'free'
is_verified     BOOLEAN DEFAULT false
is_active       BOOLEAN DEFAULT true
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
```

**apps**
```sql
id              SERIAL PRIMARY KEY
user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE
name            VARCHAR(100) NOT NULL
subdomain       VARCHAR(63) UNIQUE NOT NULL       -- indexed
repo_url        VARCHAR NOT NULL
branch          VARCHAR DEFAULT 'main'
build_path      VARCHAR DEFAULT '.'
dockerfile_path VARCHAR DEFAULT 'Dockerfile'
container_port  INTEGER NOT NULL CHECK(container_port BETWEEN 1024 AND 65535)
internal_port   INTEGER UNIQUE                   -- host port, null until first deploy
container_id    VARCHAR                          -- Docker container ID for docker stats
env             JSONB DEFAULT '{}'
status          ENUM('created','running','stopped','error','prepared') DEFAULT 'created'
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
```

**deployment_logs** (step-by-step pipeline audit)
```sql
id              SERIAL PRIMARY KEY
app_id          INTEGER REFERENCES apps(id) ON DELETE CASCADE
deploy_number   INTEGER NOT NULL               -- monotonically increasing per app
step            VARCHAR(50) NOT NULL           -- 'git_clone' | 'docker_build' | 'docker_run' | 'nginx_setup'
status          ENUM('started','success','failed')
message         TEXT
duration_ms     INTEGER
created_at      TIMESTAMPTZ DEFAULT now()

INDEX (app_id, deploy_number, created_at)
```

### 8.2 MongoDB (Log storage — append-only, TTL)

**Collection: container_logs**
```json
{
  "_id": ObjectId,
  "app_id": 42,
  "deploy_number": 3,
  "container_id": "abc123def456",
  "timestamp": ISODate("2026-04-29T10:00:01.000Z"),
  "stream": "stdout",
  "message": "Server listening on port 3000"
}
```
Indexes:
- `{ app_id: 1, timestamp: -1 }` — fast time-range queries per app
- TTL: `{ timestamp: 1 }` with `expireAfterSeconds: 2592000` (30 days)

**Collection: container_metrics** (Celery beat snapshots every 60s)
```json
{
  "_id": ObjectId,
  "app_id": 42,
  "container_id": "abc123def456",
  "timestamp": ISODate,
  "cpu_percent": 12.4,
  "memory_mb": 128.3,
  "memory_limit_mb": 512.0,
  "net_in_mb": 0.2,
  "net_out_mb": 0.1
}
```
Indexes:
- `{ app_id: 1, timestamp: -1 }`
- TTL: 7 days

### 8.3 Redis Key Schema

| Key | Type | Purpose | TTL |
|-----|------|---------|-----|
| `otp:{user_id}:{purpose}` | String | OTP code | 10 min |
| `blacklist:{jti}` | String | Revoked JWT | Remaining token lifetime |
| `rate:{ip}:{endpoint}` | INCR counter | Sliding window rate limit | 60s |
| `port_lock:{port}` | SETNX | Distributed port allocation lock | 10s |
| `pubsub:logs:{app_id}` | Pub/Sub channel | Celery → WS handler log fan-out | N/A |
| `pubsub:metrics:{app_id}` | Pub/Sub channel | Celery → WS handler metrics fan-out | N/A |

---

## 9. API Design

Base: `/api/v1`

### Auth
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | Public | Create account |
| POST | `/auth/login` | Public | Returns access + refresh tokens |
| POST | `/auth/refresh` | Refresh token | New access token |
| POST | `/auth/verify-otp` | Public | Email verification |
| POST | `/auth/forgot-password` | Public | Send password reset OTP |
| POST | `/auth/reset-password` | OTP + new password | Set new password |
| POST | `/auth/logout` | Bearer | Blacklist refresh token |

### Apps
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/apps/` | Bearer | Create app |
| GET | `/apps/` | Bearer | List own apps (paginated, ?status=running) |
| GET | `/apps/{id}` | Bearer | App detail |
| PATCH | `/apps/{id}` | Bearer | Update config fields |
| DELETE | `/apps/{id}` | Bearer | Full cleanup |
| POST | `/apps/{id}/deploy` | Bearer | Trigger deploy pipeline |
| POST | `/apps/{id}/restart` | Bearer | Restart container |
| POST | `/apps/{id}/stop` | Bearer | Stop container |

### Subdomains
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/subdomains/check?name=x` | Bearer | `{ "available": true }` |
| PATCH | `/apps/{id}/subdomain` | Bearer | Change subdomain |

### Logs
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/apps/{id}/deployments` | Bearer | Deploy history list |
| GET | `/apps/{id}/deployments/{n}/logs` | Bearer | Step logs for deploy #n |
| GET | `/apps/{id}/logs?from=&to=&limit=&cursor=` | Bearer | Container log query |

### Metrics
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/metrics/host` | Bearer | Current host snapshot |
| GET | `/apps/{id}/metrics` | Bearer | Current container snapshot |
| GET | `/apps/{id}/metrics/history?window=1h` | Bearer | Historical from MongoDB |

### Admin
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin/users` | ADMIN | All users |
| PATCH | `/admin/users/{id}` | ADMIN | Enable/disable |
| GET | `/admin/apps` | ADMIN | All apps |
| POST | `/admin/apps/{id}/force-stop` | ADMIN | Force stop |

### Error Response (consistent across all endpoints)
```json
{
  "error": "APP_NOT_FOUND",
  "detail": "App with id=42 does not exist or does not belong to you.",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 10. WebSocket Design

Auth: pass JWT as query param `?token={access_token}` (browsers can't set WS headers).

### `/ws/metrics/host` — Host-level metrics (all authenticated users)
Pushed every 5s by a background asyncio task.
```json
{
  "type": "host_metrics",
  "timestamp": "2026-04-29T10:00:00Z",
  "cpu": { "percent": 34.2, "count": 4 },
  "memory": { "total_mb": 8192, "used_mb": 4200, "percent": 51.3 },
  "disk": { "total_gb": 100, "used_gb": 42.1, "percent": 42.1 },
  "network": { "bytes_sent_mb": 1024.5, "bytes_recv_mb": 3200.1 }
}
```

### `/ws/apps/{id}/metrics` — Per-container metrics (owner only)
Source: Redis Pub/Sub `pubsub:metrics:{app_id}`. Published by `snapshot_metrics_task`.
```json
{
  "type": "container_metrics",
  "app_id": 42,
  "timestamp": "2026-04-29T10:00:00Z",
  "cpu_percent": 12.4,
  "memory_mb": 128.3,
  "memory_limit_mb": 512.0,
  "net_in_mb": 0.2,
  "net_out_mb": 0.1
}
```

### `/ws/apps/{id}/logs` — Live container log stream (owner only)
Source: Redis Pub/Sub `pubsub:logs:{app_id}`. Published by `log_tail_task` (Celery).
```json
{
  "type": "log_line",
  "stream": "stdout",
  "message": "Server listening on port 3000",
  "timestamp": "2026-04-29T10:00:01Z"
}
```

### Why Redis Pub/Sub as the Bridge
```
Celery worker: docker logs -f {container_id}
  → for each line: redis.publish("pubsub:logs:{app_id}", json)

FastAPI WS handler:
  → subscriber = await redis.subscribe("pubsub:logs:{app_id}")
  → async for message in subscriber: await ws.send_text(message)
```

This keeps the API server **stateless** — it holds no subprocesses. Multiple browser tabs subscribe to the same channel independently. This is how Slack, Discord, and similar systems fan-out messages to many connected clients.

---

## 11. Deployment Pipeline Design

### Deploy = Celery Chain

```
POST /apps/{id}/deploy
  → deploy_service.trigger(app_id) → enqueues Celery chain → returns { "task_id": "..." }

chain(
  clone_or_pull.s(app_id),
  docker_build.s(app_id),
  allocate_and_run.s(app_id),
  nginx_setup.s(app_id)
)
```

If any task raises, the chain stops. The `on_failure` handler for each task sets `app.status = ERROR`.

### Per-Step Behavior

| Step | On Success | On Failure |
|------|------------|------------|
| `clone_or_pull` | status = PREPARED | status = ERROR, log reason |
| `docker_build` | image ready in local registry | status = ERROR |
| `allocate_and_run` | port assigned, container_id stored, status = RUNNING | status = ERROR, port released |
| `nginx_setup` | conf written + nginx reloaded | WARNING log only — app still runs |

Each task bookends a `deployment_log` row: one row at START (status=started), updated at END (status=success/failed, duration_ms).

### Port Allocation — Concurrency Safety (Interview Question)
This is a classic **distributed locking** problem:

1. `SELECT internal_port FROM apps WHERE internal_port IS NOT NULL FOR UPDATE SKIP LOCKED`
   — PostgreSQL row-level lock prevents two concurrent transactions from reading the same set of used ports
2. Scan 10000–65535, skip used ports
3. `SETNX port_lock:{port} 1 EX 10` — Redis distributed lock as secondary guard
4. `socket.bind(("0.0.0.0", port))` — OS-level final check
5. `COMMIT` — port durably assigned

Why three checks? Defense in depth. DB lock handles concurrency. Redis SETNX handles the window between DB check and commit. Socket check handles OS-level surprises.

---

## 12. Logging System Design

### Three Separate Concerns

| Log Type | Storage | Who Writes It | Who Queries It |
|----------|---------|--------------|----------------|
| Application logs (internal events) | stdout → Docker/systemd | Python `logging` middleware | Ops team (Grafana Loki, etc.) |
| Deployment audit logs | PostgreSQL `deployment_logs` | Celery tasks | Users via API |
| Container runtime logs | MongoDB `container_logs` | Celery `log_tail_task` | Users via API + WS |

### Application Log Format (NFR-OBS-01)
Using `python-json-logger`:
```json
{
  "timestamp": "2026-04-29T10:00:00.123Z",
  "level": "INFO",
  "logger": "app.services.deploy_service",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": 42,
  "message": "Deploy triggered for app_id=7",
  "app_id": 7
}
```

### Correlation ID Pattern
```python
# core/logging.py
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# core/middleware.py — RequestIDMiddleware
async def dispatch(self, request, call_next):
    rid = str(uuid4())
    request_id_var.set(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

# In any service function:
logger.info("Deploying", extra={"request_id": request_id_var.get(), "user_id": user_id})
```

The `request_id` flows automatically through every log call in the same request — no need to pass it as a function argument.

### Container Log Query (Cursor Pagination)
```
GET /apps/{id}/logs?from=2026-04-29T00:00Z&to=2026-04-29T23:59Z&limit=200&cursor={last_objectid}
```
- Cursor = last `_id` from previous page.
- Query: `find({ app_id: {id}, timestamp: { $gte: from, $lte: to }, _id: { $gt: cursor } }).limit(200)`
- Returns `{ logs: [...], next_cursor: "..." | null }`

**Why cursor and not offset?** `skip(offset)` in MongoDB scans all skipped documents — O(n). Cursor-based pagination using `_id` is O(log n) via index traversal.

---

## 13. Subdomain Management

### Validation
```python
import re
SUBDOMAIN_RE = re.compile(r'^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$')
RESERVED = {"www", "api", "admin", "mail", "ftp", "smtp", "static", "assets", "docs"}
```

### Change Flow
1. Client: `GET /subdomains/check?name=myapp` → `{ "available": true }`
2. Client: `PATCH /apps/{id}/subdomain { "subdomain": "myapp" }`
3. Server:
   - Validate regex → 422 if fails
   - Check reserved list → 400 if reserved
   - `SELECT COUNT(*) FROM apps WHERE subdomain='myapp' AND id != {id}` → 409 if taken
   - `SELECT status FROM apps WHERE id={id}` → 409 "stop the app first" if RUNNING
   - Atomic: update DB → remove old conf → write new conf → `nginx -s reload`

---

## 14. Security Design

### Auth Token Flow
```
Login → access_token (15min, contains user_id + role + jti)
      + refresh_token (7 days, stored hash in Redis: user:{id}:refresh)

Each request: Authorization: Bearer {access_token}
Expired access: POST /auth/refresh → new access_token
Logout: jti → Redis blacklist (TTL = remaining access_token lifetime)
```

**Why short access + long refresh?**
Access token is stateless — validated by signature, no DB lookup. If stolen: 15min damage window.
Refresh token is long-lived but server-tracked in Redis — immediately revocable.

### Attack Surface Summary

| Input | Threat | Mitigation |
|-------|--------|-----------|
| `repo_url` | SSRF (target internal IPs) | Must start with `https://github.com/`, GitHub API validates before git clone |
| `subdomain` | Nginx config injection | Server-side `^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$` regex before any file write |
| `env` values | Stored and executed | Stored in JSONB, passed via `docker run --env` (not shell-interpolated) |
| `container_port` | Claim system port | `CHECK(container_port BETWEEN 1024 AND 65535)` at DB level |
| Login endpoint | Brute force | Rate limit: 5 attempts per IP per minute via Redis sliding window |

---

## 15. Tech Stack Decisions

### FastAPI vs Django — Keep FastAPI

**The reasoning:**
- gitDeploy is fundamentally async: WebSocket connections held open for minutes, docker/git subprocess calls, concurrent deploys.
- Django's ORM is synchronous. Django Channels adds WebSocket support but requires you to fight the synchronous default.
- FastAPI + SQLAlchemy 2.0 async + asyncpg gives you a fully async stack with zero compromises.
- Pydantic v2 integration is native to FastAPI.

**Interview answer:** "FastAPI is the right choice for an I/O-heavy, API-only service with WebSocket requirements. Django would be better if I needed its built-in admin panel, ORM migrations, or was building a server-rendered app. For a PaaS backend, FastAPI's async-first design is a better fit."

### SQLite → PostgreSQL
- SQLite: single writer lock → concurrent Celery worker + API writes cause lock timeouts.
- PostgreSQL: MVCC handles concurrent writes at the row level without contention.
- asyncpg is also ~2–3x faster than aiosqlite.

### Adding MongoDB
- Logs are append-only, variable-length, naturally expiring, potentially high-volume (thousands of lines per deploy).
- MongoDB's TTL index handles automatic purge without a cron job.
- Querying by time range with `{ app_id: 1, timestamp: -1 }` index is fast.
- Forcing this into PostgreSQL TEXT columns would work but fights the engine.

### Adding Celery
- Current v1: deploy runs inline in async route → server restart = silent deploy drop.
- Celery: tasks survive broker restart (persistent queue), are retryable, and monitorable via Flower.
- Workers are independently scalable — add more workers on the same machine or separate machines.

---

## 16. Glossary

| Term | Definition |
|------|------------|
| App | A user's deployed GitHub repo, one row in `apps` table |
| Internal Port | The host OS port that maps to the container (10000–65535, allocated per deploy) |
| Container Port | The port the application inside the container listens on (user-specified) |
| Subdomain | The `{name}.gitdeploy.online` hostname for an app |
| Deploy | The full pipeline: clone → build → run → nginx configure |
| Celery Chain | Sequential Celery tasks where failure stops the chain |
| Fan-Out | Redis Pub/Sub pattern: one publisher, many subscribers get the same message |
| Pub/Sub | Redis publish/subscribe — producer publishes to a channel, subscribers receive |
| WS | WebSocket — persistent full-duplex connection between browser and server |
| Celery Beat | Celery's built-in cron scheduler (used for log purge, metrics snapshots) |
| TTL Index | MongoDB index that auto-deletes documents after a specified duration |
| jti | JWT ID — unique per-token claim, used to blacklist tokens on logout |
| MVCC | Multi-Version Concurrency Control — PostgreSQL's method for non-blocking concurrent reads/writes |
| Cursor Pagination | Pagination using last-seen ID as a pointer (O(log n) vs offset's O(n)) |
| asyncpg | High-performance async PostgreSQL driver |
| Motor | Official async MongoDB driver for Python |
| ContextVar | Python 3.7+ mechanism for async-context-local variables (like request_id) |
