# gitDeploy — Current Progress & What To Do Next

> Last reviewed: 2026-03-12
> Code last changed: unchanged since auth implementation

---

## Table of Contents

1. [Where You Are Right Now](#1-where-you-are-right-now)
2. [Full System Flow (Target Architecture)](#2-full-system-flow-target-architecture)
3. [Phase 0 — Fix Critical Bugs (Do This First)](#3-phase-0--fix-critical-bugs-do-this-first)
4. [Phase 1 — Database Migration Setup](#4-phase-1--database-migration-setup)
5. [Phase 2 — Docker + Traefik Setup](#5-phase-2--docker--traefik-setup)
6. [Phase 3 — Frontend (React)](#6-phase-3--frontend-react)
7. [Phase 4 — Tests](#7-phase-4--tests)
8. [Complete Step-by-Step Execution Order](#8-complete-step-by-step-execution-order)
9. [File Change Reference](#9-file-change-reference)

---

## 1. Where You Are Right Now

### What's Built and Working ✅

```
gitDeploy/
├── FastAPI app (main.py)              ✅  Running, CORS configured
├── app/
│   ├── config.py                      ✅  Loads .env properly
│   ├── database.py                    ⚠️  SQLAlchemy deprecated import
│   ├── constants.py                   ✅  AppStatus, UserRoles, BillingType enums
│   ├── utils.py                       ✅  bcrypt hashing, OAuth2 scheme
│   ├── models/
│   │   ├── app_model.py               ✅  Apps table with user_id FK
│   │   ├── users.py                   ⚠️  role default is wrong type
│   │   ├── error_log.py               ⚠️  created_at bug
│   │   └── timestatus_mixin.py        ✅  Timestamps on all models
│   ├── schemas/                       ✅  All Pydantic schemas exist
│   │   └── app_detail_schema.py       ⚠️  internal_port not Optional
│   ├── services/
│   │   ├── auth.py                    ✅  JWT create/decode/get_current_user
│   │   ├── deploy.py                  ✅  Git clone/pull/branch — minor double-call bug
│   │   ├── docker.py                  ⚠️  Errors swallowed silently
│   │   ├── docker_command_builder.py  ✅  Builder pattern, clean
│   │   └── port_manager.py            ✅  Dynamic port allocation
│   └── Errors/                        ✅  20+ error classes, global handler, DB logging
├── api/v1/
│   ├── auth.py                        ✅  register / login / refresh / logout / me
│   └── apps.py                        ✅  create / list / get / delete / deploy
└── migrations/                        ⚠️  Alembic initialized, no versions yet
```

### What's NOT Built Yet ❌

```
❌  Docker Compose file           (no docker-compose.yml)
❌  Traefik config                (no traefik setup at all)
❌  Frontend / React UI           (zero front-end code)
❌  Alembic migration versions    (tables created by create_all, not tracked)
❌  Tests                         (zero test files)
❌  Production .env               (only dev .env exists)
```

### Completion Score

```
██████████░░░░░░░░░░  ~50%

Done:   Backend API, Auth, Docker engine, Git engine, Error system, Port manager
Gaps:   Infra (Traefik/Docker), Frontend, Tests, Migrations, Production config
```

---

## 2. Full System Flow (Target Architecture)

This is what the finished product looks like end-to-end:

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                         INTERNET                                        │
 └────────────────────────────┬────────────────────────────────────────────┘
                              │  *.yourdomain.com
                              ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                    CLOUDFLARE (Edge Layer)                              │
 │  SSL/TLS termination · DDoS protection · WAF · CDN                     │
 │  DNS wildcard: *.yourdomain.com → your server IP                       │
 └────────────────────────────┬────────────────────────────────────────────┘
                              │  HTTP (Cloudflare tunnel)
                              ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                    YOUR VPS / SERVER                                    │
 │                                                                         │
 │  ┌─────────────────────────────────────────────────────────────────┐   │
 │  │                    TRAEFIK  :80 / :443                          │   │
 │  │  Reads Docker labels · Routes by hostname · Load balances       │   │
 │  │  dashboard.yourdomain.com → frontend container                  │   │
 │  │  api.yourdomain.com       → backend container                   │   │
 │  │  app-abc.yourdomain.com   → user app container (port 10001)     │   │
 │  │  app-xyz.yourdomain.com   → user app container (port 10002)     │   │
 │  └───────┬──────────────┬──────────────────────┬───────────────────┘   │
 │          │              │                      │                       │
 │          ▼              ▼                      ▼                       │
 │  ┌──────────────┐ ┌──────────────┐  ┌────────────────────────────┐    │
 │  │   FRONTEND   │ │   BACKEND    │  │   USER APP CONTAINERS       │    │
 │  │  React/Vite  │ │  FastAPI     │  │  app-abc  app-xyz  app-...  │    │
 │  │  :3000       │ │  :8000       │  │  :10001   :10002   :10003   │    │
 │  └──────────────┘ └──────┬───────┘  └────────────────────────────┘    │
 │                          │                                             │
 │                          ▼                                             │
 │  ┌──────────────────────────────────────────────────────────────┐      │
 │  │                    SQLITE  (test.db)                         │      │
 │  │         users · apps · error_logs tables                     │      │
 │  └──────────────────────────────────────────────────────────────┘      │
 │                                                                         │
 │  /opt/apps/{app_id}/   ← cloned repos live here                        │
 │  /opt/logs/{app_id}/   ← build + runtime logs                          │
 └─────────────────────────────────────────────────────────────────────────┘
```

### Request Flow: User Deploys an App

```
USER BROWSER                FRONTEND               BACKEND               DOCKER
     │                          │                     │                     │
     │  Fill deploy form        │                     │                     │
     │─────────────────────────►│                     │                     │
     │                          │  POST /apps/create  │                     │
     │                          │  Bearer: <AT>        │                     │
     │                          │────────────────────►│                     │
     │                          │                     │  Validate GitHub URL│
     │                          │                     │  Create DB record   │
     │                          │◄────────────────────│                     │
     │                          │  { id, subdomain }  │                     │
     │                          │                     │                     │
     │  Click Deploy            │                     │                     │
     │─────────────────────────►│                     │                     │
     │                          │  POST /apps/{id}/deploy                   │
     │                          │────────────────────►│                     │
     │                          │                     │  git clone / pull   │
     │                          │                     │  status=PREPARED    │
     │                          │                     │  docker build ─────►│
     │                          │                     │                     │  build image
     │                          │                     │  docker run ───────►│
     │                          │                     │                     │  start container
     │                          │                     │  allocate port      │  :10001
     │                          │                     │  status=RUNNING     │
     │                          │◄────────────────────│                     │
     │                          │  { status: RUNNING }│                     │
     │◄─────────────────────────│                     │                     │
     │  "Your app is live at    │                     │                     │
     │   app-abc.yourdomain.com"│                     │                     │
```

---

## 3. Phase 0 — Fix Critical Bugs (Do This First)

**None of these require new features — they are bugs that make the existing code break.**
Fix all of them before doing anything else.

---

### Bug 1 — SQLAlchemy Deprecated Import (Breaks on install)

**File:** `app/database.py`

```python
# ❌ CURRENT — removed in SQLAlchemy 2.x
from sqlalchemy.ext.declarative import declarative_base

# ✅ FIX
from sqlalchemy.orm import declarative_base
```

---

### Bug 2 — Users.role Default Type Mismatch

**File:** `app/models/users.py`

```python
# ❌ CURRENT — string "user", but column expects UserRoles enum
role = Column(Enum(UserRoles), default="user")

# ✅ FIX
from app.constants import UserRoles
role = Column(Enum(UserRoles), default=UserRoles.USER)
```

---

### Bug 3 — internal_port Not Optional in AppDetail Schema

**File:** `app/schemas/app_detail_schema.py`

```python
# ❌ CURRENT — breaks GET /apps/{id} on freshly created (not-yet-deployed) apps
internal_port: int

# ✅ FIX
from typing import Optional
internal_port: Optional[int] = None
```

---

### Bug 4 — ErrorLog.created_at Uses datetime.now() at Class Load Time

**File:** `app/models/error_log.py`

```python
# ❌ CURRENT — all rows get same timestamp (evaluated once when Python loads the class)
created_at = Column(DateTime, default=datetime.now())

# ✅ FIX — pass the function reference, not the result
from datetime import datetime
created_at = Column(DateTime, default=datetime.utcnow)
```

---

### Bug 5 — docker_remove_container Swallows Errors Silently

**File:** `app/services/docker.py`

```python
# ❌ CURRENT — failure is hidden, next deploy may fail with stale container
try:
    subprocess.run(cmd)
except:
    pass

# ✅ FIX — log the error at minimum
import logging
logger = logging.getLogger(__name__)

try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"docker remove failed: {result.stderr}")
except Exception as e:
    logger.error(f"docker_remove_container exception: {e}")
```

---

### Bug 6 — Double GitHub API Call on Deploy

**File:** `app/services/deploy.py`

```python
# ❌ CURRENT — validate_github_repo is called INSIDE clone_or_pull_repo
# but also called before it in apps.py → two GitHub API calls per deploy

# ✅ FIX — remove the internal call from clone_or_pull_repo
# Let apps.py handle validation once, before calling clone_or_pull_repo
```

---

### All Bugs At a Glance

| # | File | Severity | Impact |
|---|------|----------|--------|
| 1 | `app/database.py` | 🔴 Critical | App won't start on SQLAlchemy 2.x |
| 2 | `app/models/users.py` | 🔴 Critical | Register fails with type error |
| 3 | `app/schemas/app_detail_schema.py` | 🔴 Critical | GET /apps/{id} crashes before first deploy |
| 4 | `app/models/error_log.py` | 🟡 Medium | All error logs have wrong timestamp |
| 5 | `app/services/docker.py` | 🟡 Medium | Silent failures hide real errors |
| 6 | `app/services/deploy.py` | 🟢 Low | Wasted GitHub API calls |

---

## 4. Phase 1 — Database Migration Setup

Right now, tables are created by `Base.metadata.create_all()` at startup — this means schema changes wipe your data or are ignored. Set up Alembic properly.

### Steps

```bash
# 1. Make sure alembic.ini points to your DB correctly
#    Open alembic.ini and verify:
#    sqlalchemy.url = sqlite:///./test.db

# 2. Make sure migrations/env.py imports your models
#    Open migrations/env.py and verify target_metadata uses your Base:
```

```python
# migrations/env.py — verify this block exists
from app.database import Base
from app.models import app_model, users, error_log   # import all models

target_metadata = Base.metadata
```

```bash
# 3. Create the first migration snapshot
alembic revision --autogenerate -m "initial schema"

# 4. Apply it (this creates the tables properly tracked)
alembic upgrade head

# 5. For every future schema change:
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

### After This

- `test.db` is managed by Alembic
- Schema changes are reversible (`alembic downgrade -1`)
- No more "table already exists" crashes

---

## 5. Phase 2 — Docker + Traefik Setup

This is the infrastructure layer. Without it, deployed apps have no public URL.

### Step 1 — Create `docker-compose.yml`

Create at project root:

```yaml
# docker-compose.yml
version: "3.9"

networks:
  web:
    external: true   # Traefik uses this network to reach all containers

services:

  # ── Traefik (reverse proxy + load balancer) ──────────────────────────────
  traefik:
    image: traefik:v3.0
    container_name: traefik
    restart: unless-stopped
    command:
      - "--api.dashboard=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--providers.docker.network=web"
      - "--entrypoints.web.address=:80"
      # Future: add --entrypoints.websecure.address=:443 when ready
    ports:
      - "80:80"
      - "8080:8080"    # Traefik dashboard (restrict in production)
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - web
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.dashboard.rule=Host(`traefik.yourdomain.com`)"
      - "traefik.http.routers.dashboard.service=api@internal"

  # ── Backend (FastAPI) ─────────────────────────────────────────────────────
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: gitdeploy-backend
    restart: unless-stopped
    env_file: .env
    volumes:
      - /opt/apps:/opt/apps     # cloned repos
      - /opt/logs:/opt/logs     # build logs
      - /var/run/docker.sock:/var/run/docker.sock  # backend controls Docker
      - ./test.db:/app/test.db  # SQLite persistence
    networks:
      - web
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`api.yourdomain.com`)"
      - "traefik.http.services.api.loadbalancer.server.port=8000"

  # ── Frontend (React/Vite) ─────────────────────────────────────────────────
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.frontend
    container_name: gitdeploy-frontend
    restart: unless-stopped
    networks:
      - web
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.app.rule=Host(`yourdomain.com`) || Host(`www.yourdomain.com`)"
      - "traefik.http.services.app.loadbalancer.server.port=3000"
```

---

### Step 2 — Create `Dockerfile.backend`

```dockerfile
# Dockerfile.backend
FROM python:3.12-slim

WORKDIR /app

# Install system deps (needed for bcrypt + git)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create dirs
RUN mkdir -p /opt/apps /opt/logs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### Step 3 — Traefik Labels for User-Deployed Apps

When your backend deploys a user app, it must add Traefik labels to the container so it gets a public URL automatically.

**In `app/services/docker.py` — update `docker_run`:**

```python
def docker_run(app_model, app_dir, **kwargs):
    subdomain = app_model.subdomain   # e.g. "app-abc"
    domain = "yourdomain.com"         # pull from config

    builder = (
        DockerCommandBuilder.RunCommandBuilder()
        .run()
        .detached()
        .with_name(f"gitdeploy-{app_model.id}")
        .with_port_mapping(app_model.internal_port, app_model.container_port)

        # ── Traefik labels ──────────────────────────────────────────────────
        .with_label("traefik.enable=true")
        .with_label(f"traefik.http.routers.{subdomain}.rule=Host(`{subdomain}.{domain}`)")
        .with_label(f"traefik.http.services.{subdomain}.loadbalancer.server.port={app_model.container_port}")

        # ── Health check ────────────────────────────────────────────────────
        .with_healthcheck("/health", interval="30s", timeout="10s", retries=3)

        .with_image(f"gitdeploy-{app_model.id}:latest")
        .compile()
    )
    # ... rest of run logic
```

---

### Step 4 — Create the Docker network once

```bash
# Run this ONCE on your server before `docker compose up`
docker network create web
```

---

### Step 5 — Start Everything

```bash
docker compose up -d
```

---

### Traefik Routing Summary

```
Request: app-abc.yourdomain.com
    │
    ▼ Traefik reads labels of all running containers
    │
    └── finds container with label:
        traefik.http.routers.app-abc.rule=Host(`app-abc.yourdomain.com`)
    │
    ▼
Container app-abc on port 10001
```

**No config reload needed.** Start container with correct labels → Traefik picks it up in ~1 second.

---

## 6. Phase 3 — Frontend (React)

> Hand `docs/FRONTEND_SPEC.md` to your UI developer.
> Below is what the frontend needs to implement to work with current APIs.

### Pages Required

```
/login          → POST /api/v1/auth/login
/signup         → POST /api/v1/auth/register
/dashboard      → GET  /api/v1/apps/list/
/apps/new       → POST /api/v1/apps/create
/apps/:id       → GET  /api/v1/apps/:id
/apps/:id/deploy→ POST /api/v1/apps/:id/deploy
```

### Auth Flow for Frontend

```
                    FRONTEND                          BACKEND
                        │                               │
  User submits login    │  POST /api/v1/auth/login      │
  ─────────────────────►│  { email, password }           │
                        │──────────────────────────────►│
                        │◄──────────────────────────────│
                        │  { access_token }             │
                        │  Set-Cookie: refresh_token    │ ← HttpOnly, auto-managed
                        │                               │
  Store access_token    │                               │
  in memory (NOT        │                               │
  localStorage)         │                               │
                        │                               │
  Every API call        │  Authorization: Bearer <AT>   │
  ─────────────────────►│──────────────────────────────►│
                        │                               │
  AT expires (15 min)   │                               │
  ─────────────────────►│  POST /api/v1/auth/refresh    │
                        │  (cookie sent automatically)  │
                        │──────────────────────────────►│
                        │◄──────────────────────────────│
                        │  { new access_token }         │
                        │                               │
```

### Tech Stack (React)

```
Framework:    React + Vite
Routing:      React Router v6
HTTP:         Axios (with interceptor for auto token refresh)
State:        Zustand or React Context
Styling:      Tailwind CSS (reference: Vercel's clean UI)
```

### Axios Interceptor (copy-paste ready)

```javascript
// api/axiosInstance.js
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,   // http://api.yourdomain.com
  withCredentials: true,                    // sends HttpOnly refresh cookie
});

let accessToken = null;

export const setAccessToken = (token) => { accessToken = token; };

// Attach token to every request
api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const { data } = await api.post('/api/v1/auth/refresh');
      setAccessToken(data.access_token);
      original.headers.Authorization = `Bearer ${data.access_token}`;
      return api(original);
    }
    return Promise.reject(error);
  }
);

export default api;
```

### Frontend Dockerfile

```dockerfile
# frontend/Dockerfile.frontend
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config for React SPA (client-side routing)
RUN echo 'server { \
  listen 3000; \
  root /usr/share/nginx/html; \
  index index.html; \
  location / { try_files $uri $uri/ /index.html; } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 3000
```

---

## 7. Phase 4 — Tests

Minimum test set to feel confident shipping:

```
tests/
├── test_auth.py        ← register / login / refresh / logout / me
├── test_apps.py        ← create / list / get / deploy / delete
├── test_ownership.py   ← user A cannot access user B's app
└── conftest.py         ← shared DB fixture, test client
```

### conftest.py

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.dependencies import get_db
from main import app

TEST_DB_URL = "sqlite:///./test_temp.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client(setup_db):
    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)
```

### test_auth.py (example)

```python
# tests/test_auth.py
def test_register_and_login(client):
    # Register
    r = client.post("/api/v1/auth/register", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "secret123"
    })
    assert r.status_code == 200

    # Login
    r = client.post("/api/v1/auth/login", json={
        "email": "alice@example.com",
        "password": "secret123"
    })
    assert r.status_code == 200
    assert "access_token" in r.json()

def test_me_requires_auth(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401

def test_refresh_token(client):
    # Register + Login first
    client.post("/api/v1/auth/register", json={
        "username": "bob", "email": "bob@test.com", "password": "pass"
    })
    client.post("/api/v1/auth/login", json={
        "email": "bob@test.com", "password": "pass"
    })
    # Refresh (cookie is auto-sent by TestClient)
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    assert "access_token" in r.json()
```

---

## 8. Complete Step-by-Step Execution Order

Follow this exact sequence. Do not skip phases.

```
PHASE 0 — Bugs (today, ~30 min)
 │
 ├── [0.1]  Fix database.py import             app/database.py
 ├── [0.2]  Fix users.py role default          app/models/users.py
 ├── [0.3]  Fix app_detail_schema.py           app/schemas/app_detail_schema.py
 ├── [0.4]  Fix error_log.py timestamp         app/models/error_log.py
 ├── [0.5]  Fix docker.py silent errors        app/services/docker.py
 └── [0.6]  Fix deploy.py double API call      app/services/deploy.py
 │
 ▼
PHASE 1 — Database (today, ~20 min)
 │
 ├── [1.1]  Fix migrations/env.py              add model imports + target_metadata
 ├── [1.2]  Run: alembic revision --autogenerate -m "initial schema"
 └── [1.3]  Run: alembic upgrade head
 │
 ▼
PHASE 2 — Infrastructure (~1-2 hrs)
 │
 ├── [2.1]  Create docker-compose.yml          project root
 ├── [2.2]  Create Dockerfile.backend          project root
 ├── [2.3]  Add Traefik labels to docker_run   app/services/docker.py
 ├── [2.4]  Create Docker network:  docker network create web
 └── [2.5]  Test: docker compose up -d
 │
 ▼
PHASE 3 — Frontend (~3-5 days, hand to UI dev)
 │
 ├── [3.1]  Share docs/FRONTEND_SPEC.md
 ├── [3.2]  Create frontend/ directory (Vite + React)
 ├── [3.3]  Implement auth pages (login, signup)
 ├── [3.4]  Implement dashboard + app pages
 ├── [3.5]  Create frontend/Dockerfile.frontend
 └── [3.6]  Add frontend service to docker-compose.yml
 │
 ▼
PHASE 4 — Tests (~2-3 hrs)
 │
 ├── [4.1]  Create tests/conftest.py
 ├── [4.2]  Write tests/test_auth.py
 ├── [4.3]  Write tests/test_apps.py
 └── [4.4]  Write tests/test_ownership.py
 │
 ▼
PHASE 5 — Production Hardening (before going live)
 │
 ├── [5.1]  Replace SQLite → PostgreSQL
 ├── [5.2]  Add Redis for refresh token revocation
 ├── [5.3]  Add HTTPS to Traefik (Let's Encrypt or Cloudflare cert)
 ├── [5.4]  Environment-specific .env files (.env.prod)
 └── [5.5]  Add rate limiting on /auth endpoints
```

---

## 9. File Change Reference

Quick lookup of exactly which files need to change and why:

| File | Change Needed | Phase |
|------|--------------|-------|
| `app/database.py` | Fix deprecated import | 0 |
| `app/models/users.py` | Fix role default type | 0 |
| `app/schemas/app_detail_schema.py` | Make internal_port Optional | 0 |
| `app/models/error_log.py` | Fix created_at default | 0 |
| `app/services/docker.py` | Log errors + add Traefik labels | 0 + 2 |
| `app/services/deploy.py` | Remove double API call | 0 |
| `migrations/env.py` | Add model imports + target_metadata | 1 |
| `docker-compose.yml` | CREATE NEW | 2 |
| `Dockerfile.backend` | CREATE NEW | 2 |
| `frontend/Dockerfile.frontend` | CREATE NEW | 3 |
| `tests/conftest.py` | CREATE NEW | 4 |
| `tests/test_auth.py` | CREATE NEW | 4 |
| `tests/test_apps.py` | CREATE NEW | 4 |

---

*gitDeploy — progress guide last generated: 2026-03-12*
