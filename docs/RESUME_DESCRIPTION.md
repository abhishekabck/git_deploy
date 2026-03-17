# gitDeploy — Resume Project Description

## Short Description (1-2 lines for resume bullet)

Built a self-hosted Platform-as-a-Service (PaaS) with FastAPI and React that automates Docker-based deployment of GitHub repositories with subdomain routing, JWT authentication, and an admin monitoring dashboard.

---

## Project Summary (for portfolio / LinkedIn)

**gitDeploy** is a full-stack self-hosted deployment platform inspired by Vercel and Railway, built from scratch as a personal project. The system accepts a GitHub repository URL, automatically builds a Docker image from the project's Dockerfile, runs it as an isolated container, and exposes it publicly via a unique subdomain — all without manual server configuration.

The project spans the full stack: an async Python backend managing the deployment lifecycle, a React frontend with a live admin dashboard, a companion sidecar service for encrypted secret storage, and infrastructure automation scripts for Nginx subdomain routing and Cloudflare Tunnel integration.

---

## Technical Highlights

### Backend (Python / FastAPI)

- Designed and implemented a fully **asynchronous REST API** using FastAPI with SQLAlchemy 2.0 async ORM (aiosqlite for development, asyncpg for production). Every database operation, HTTP request, and I/O call is non-blocking.
- Built a **layered architecture** with clear separation of concerns: API routes handle HTTP concerns only; a service layer owns all business logic and orchestration; a data layer manages ORM models and sessions.
- Implemented **JWT authentication** with short-lived access tokens (15 min) and long-lived refresh tokens stored as HttpOnly, path-scoped cookies — preventing XSS token theft and limiting cookie exposure to only the `/auth/refresh` endpoint.
- Created a **custom error framework** with categorised numeric error codes (1xxx Git, 2xxx Docker, 3xxx App, 4xxx DB, 5xxx Internal), persistent structured error logging to a database table, and a global exception handler middleware.
- Developed a **Docker automation service** using `subprocess` + `asyncio.to_thread()` to programmatically build images, run containers with resource limits and custom labels, and manage the full container lifecycle — without blocking the async event loop.
- Built a **dynamic port allocator** that simultaneously queries the database (for previously allocated ports) and the host OS socket table (via psutil) to guarantee collision-free port assignment across the 10,000–65,535 range, even under concurrent deployments.
- Implemented an **optional Redis caching layer** with namespacing (`gitdeploy:`) to coexist safely with other Redis tenants. All cache operations have a graceful no-op fallback if Redis is unavailable.
- Used **Alembic** for production-grade database schema migrations with a fully async-compatible migration environment.

### Sidecar Service

- Designed a **secret manager companion service** following the sidecar pattern — a separate FastAPI process on port 8001 with its own database and encryption key, communicating with the main API over HTTP with a shared API key.
- Uses **Fernet symmetric encryption** (AES-128-CBC + HMAC-SHA256) for at-rest secret storage. Plain-text secrets are never written to disk.
- Implemented a **key rotation endpoint** that atomically re-encrypts all stored secrets under a new key without service downtime.

### Infrastructure Automation

- Automated **Nginx subdomain routing** via shell scripts that generate per-app `server {}` blocks in `/etc/nginx/gitdeploy.d/`, validate config, and reload Nginx — triggered automatically after each deployment.
- Configured **Cloudflare Tunnel** integration (zero open inbound ports) with a wildcard `*.domain.com` DNS entry routing through the tunnel to Nginx and then to containers.

### Frontend (React)

- Built with **React 19 + Vite**, Tailwind CSS, React Query (TanStack), Zustand, React Hook Form + Zod.
- Implemented **silent token refresh** via Axios interceptors — on a 401 response, failed requests are queued, a single refresh call is made, and all queued requests are retried with the new token automatically. Concurrent 401s during the refresh window are handled correctly.
- Built a fully functional **Admin Dashboard** with live system health metrics (CPU, memory, disk, network) polling every 15 seconds, app management across all users, user role management, and a structured error log viewer.
- Stored access tokens **in memory only** (Zustand store) — never in localStorage — to prevent XSS token theft.

### Key Design Decisions

- Chose **async SQLAlchemy 2.0** over the synchronous API to support multiple concurrent deployments without database session contention.
- Used **`asyncio.to_thread()`** to offload all blocking subprocess calls (git clone, docker build) to a thread pool, keeping the event loop free for other requests during long-running builds.
- Chose **SQLite as default** with a transparent zero-code-change upgrade path to PostgreSQL (driver detection from the URL string), lowering the barrier to getting started.
- Applied the **sidecar pattern** to isolate secret management: the sidecar can be upgraded, replaced, or scaled independently of the main API.

---

## Stack

`Python 3.12` · `FastAPI` · `SQLAlchemy 2.0 (async)` · `aiosqlite` · `asyncpg` · `Alembic` · `React 19` · `Vite` · `Tailwind CSS` · `Zustand` · `React Query` · `Docker` · `Nginx` · `Cloudflare Tunnel` · `JWT` · `bcrypt` · `Redis` · `aioredis` · `Fernet encryption` · `psutil` · `httpx` · `Pydantic v2`

---

## What I Learned

- Deep understanding of **async Python patterns**: asyncio event loop behaviour, `async context managers`, `asyncio.to_thread()` for blocking I/O, and async SQLAlchemy session management.
- Production **JWT security practices**: why access tokens should be short-lived, why refresh tokens belong in HttpOnly cookies rather than localStorage, and why path-scoping the refresh cookie matters.
- **Docker automation**: building images programmatically, managing container lifecycle, applying labels for operational identification, log rotation, and handling partial failure cleanup.
- **Nginx configuration management**: dynamic vhost generation, include-based config organisation, and safe reload patterns.
- **Cloudflare Tunnel architecture**: zero-trust network access, wildcard DNS routing, and the cloudflared daemon lifecycle.
- **Sidecar microservice pattern**: how to design a companion service with its own persistence and encryption, and how the two services authenticate to each other.
- **React Query** patterns for server-state management: cache invalidation after mutations, background refetching, and loading/error states.
- The practical difference between **SQLite concurrency limitations** and PostgreSQL's MVCC model, and when each is appropriate.
- How to design **layered architecture** in a FastAPI application so that route handlers stay thin, service functions are independently testable, and infrastructure concerns are isolated at the bottom layer.
