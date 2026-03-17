# Software Requirements Specification — gitDeploy

**Document version:** 2.0
**Date:** 2026-03-17
**Status:** Approved

---

## Table of Contents

1. Introduction
2. Overall Description
3. Specific Requirements
4. Non-Functional Requirements
5. System Constraints
6. External Interface Requirements

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) defines the functional and non-functional requirements for gitDeploy v2.0, a self-hosted Platform as a Service (PaaS). The document is intended for developers contributing to the project, system administrators operating the platform, and evaluators assessing the system.

### 1.2 Scope

gitDeploy enables registered users to deploy public GitHub repositories as containerised applications on a host server. The system handles the full lifecycle: repository validation, code cloning, Docker image building, container execution, network routing, and secret management. Users interact through a REST API and a React-based web dashboard. An administrator role provides system-wide visibility and control.

The system does not:
- Support private GitHub repositories (current version)
- Manage DNS records automatically (only generates Nginx and Cloudflare Tunnel configuration)
- Provide billing or payment processing (the `billing_type` field is a placeholder for future use)
- Orchestrate containers across multiple hosts (single-server deployment only)

### 1.3 Definitions, Acronyms, and Abbreviations

| Term          | Definition                                                                                   |
|---------------|----------------------------------------------------------------------------------------------|
| App           | A deployable unit consisting of a GitHub repository, Docker configuration, and runtime state |
| Container     | A Docker container running an app image                                                       |
| Internal port | The host-side port (10000–65535) mapped to the container's exposed port                      |
| Container port| The port the application inside the container listens on                                     |
| Subdomain     | The `app-{id}.DOMAIN` address assigned to each deployed app                                  |
| Sidecar       | The Secret Manager companion service running alongside the main API                           |
| PaaS          | Platform as a Service                                                                         |
| JWT           | JSON Web Token                                                                                |
| ORM           | Object-Relational Mapper                                                                      |
| DFD           | Data Flow Diagram                                                                             |

### 1.4 References

- FastAPI documentation: https://fastapi.tiangolo.com
- SQLAlchemy 2.0 async documentation: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Docker CLI reference: https://docs.docker.com/engine/reference/commandline/docker/
- Cloudflare Tunnel documentation: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
- Fernet specification: https://github.com/fernet/spec

### 1.5 Document Overview

- Section 2 describes the product context, major functions, and user types.
- Section 3 specifies detailed functional requirements per module.
- Section 4 specifies non-functional requirements.
- Section 5 lists system constraints.
- Section 6 describes external interface requirements.

---

## 2. Overall Description

### 2.1 Product Perspective

gitDeploy is a standalone web service deployed on a single Linux server. It exposes a REST API consumed by a React frontend and by direct API clients. It orchestrates three external subsystems: the Git CLI, the Docker daemon, and optionally Nginx. An optional Cloudflare Tunnel sits in front of Nginx to route public internet traffic without exposing TCP ports.

```
Internet User
     |
     | HTTPS
     v
Cloudflare Edge  ──(tunnel)──>  Nginx :80  ──>  Docker container :internal_port
                                               (app-N.domain.com)

Registered User
     |
     | HTTPS
     v
React Frontend  ──>  gitDeploy API :8000  ──>  DB (SQLite/PG)  ──>  Docker / Git
                                          ──>  Secret Sidecar :8001
                                          ──>  Redis (optional)
```

### 2.2 Product Functions

The following are the high-level functions of the system:

1. **User registration and authentication** — create accounts, authenticate with credentials, maintain sessions using JWT access and refresh tokens.
2. **App registration** — record a user's intent to deploy a GitHub repository; validate the repository URL; assign a subdomain.
3. **App deployment** — clone or update the source code, build a Docker image, allocate a host port, run a container, write Nginx routing configuration.
4. **App management** — list, inspect, redeploy, and delete owned apps.
5. **Secret management** — store and retrieve encrypted per-app environment variables via the sidecar service.
6. **Administration** — monitor system health, manage all apps and users, view error logs.
7. **Error tracking** — capture and persist error events with structured codes and context.
8. **Optional caching** — accelerate read-heavy operations via Redis with namespace isolation.

### 2.3 User Classes and Characteristics

**Regular User**
- Registers and authenticates via the web UI or API
- Creates, deploys, and deletes their own apps
- Cannot access other users' apps or system-wide data
- Interacts primarily through the React frontend

**Administrator**
- Has `role=admin` in the database
- Can view and manage all apps and all users across the system
- Can force-delete any app or user (with full resource cleanup)
- Can view the system error log and health metrics
- Typically a server operator; may use the API directly or the admin section of the frontend

**Machine Client (API consumer)**
- Authenticates using a static `VALID_API_KEY` header (optional)
- Suitable for CI/CD pipeline integrations

### 2.4 Operating Environment

- **Server OS:** Linux (Ubuntu 20.04+ recommended)
- **Python:** 3.12+
- **Docker Engine:** 24.0+ installed and accessible to the user running the API process
- **Git:** 2.x installed and on PATH
- **Database:** SQLite (development and small deployments) or PostgreSQL 14+ (production)
- **Redis:** 6.0+ (optional)
- **Nginx:** 1.18+ (optional, required for subdomain routing)
- **Cloudflare Tunnel:** cloudflared binary (optional, required for zero-port-forward public access)

### 2.5 Design and Implementation Constraints

- The backend must remain fully asynchronous; blocking I/O must be wrapped in `asyncio.to_thread`.
- Authentication must use JWT; no server-side session storage is permitted.
- The error system must use the established numeric code ranges (1xxx-5xxx).
- All environment-specific configuration must be read from environment variables; no hardcoded secrets.
- The sidecar must run as a completely separate process with its own database.

### 2.6 Assumptions and Dependencies

- The server has outbound internet access to reach `api.github.com` for repository validation.
- The Docker daemon socket is accessible to the process running gitDeploy (typically via group membership or running as root).
- Port range 10000–65535 is not blocked by a firewall for internal loopback traffic.
- Nginx is configured to include files from `NGINX_CONF_DIR` when `NGINX_ENABLED=true`.

---

## 3. Specific Requirements

### 3.1 Authentication Module

**FR-AUTH-01 — User Registration**
The system shall accept a `POST /api/v1/auth/register` request with `username`, `email`, and `password`. It shall validate that the email and username are not already registered (HTTP 409 on conflict). On success it shall store a bcrypt-hashed password and return the user profile with HTTP 201.

**FR-AUTH-02 — User Login**
The system shall accept a `POST /api/v1/auth/login` request with `email` and `password`. It shall verify the credentials against the stored bcrypt hash. On success it shall:
- Return an access token (HS256 JWT, `ACCESS_TOKEN_EXPIRE_MINUTES` TTL) in the JSON response body.
- Set a `refresh_token` HttpOnly cookie scoped to `/api/v1/auth/refresh` with `max_age = REFRESH_TOKEN_EXPIRE_DAYS * 86400`.

**FR-AUTH-03 — Token Refresh**
The system shall accept a `POST /api/v1/auth/refresh` request. It shall read the `refresh_token` cookie, verify its signature and `type=refresh` claim, load the user from the database, and return a new access token. It shall return HTTP 401 if the cookie is absent, the signature is invalid, or the user no longer exists.

**FR-AUTH-04 — Logout**
The system shall accept a `POST /api/v1/auth/logout` request and respond with a `Set-Cookie` header that expires the `refresh_token` cookie immediately.

**FR-AUTH-05 — Current User**
The system shall accept a `GET /api/v1/auth/me` request with a valid Bearer access token and return the authenticated user's `id`, `username`, `email`, `role`, and `billing_type`.

**FR-AUTH-06 — Role Enforcement**
All endpoints in the admin router shall reject requests from non-admin users with HTTP 403.

### 3.2 App Management Module

**FR-APP-01 — Create App**
The system shall accept a `POST /api/v1/apps/create` request containing `name`, `repo_url`, `container_port`, and optional `branch`, `source_dir`, `dockerfile_path`, `env` fields. It shall:
- Validate that `repo_url` begins with `https://github.com/` and matches the `owner/repo` path format.
- Call the GitHub API (`https://api.github.com/repos/{owner}/{repo}`) to confirm the repository exists and is public.
- Create an `apps` database record with `status=created`.
- Assign a subdomain of the form `app-{id}` after flush.
- Return HTTP 201 with `id`, `subdomain`, `container_port`, and `status`.

**FR-APP-02 — List Apps**
The system shall accept a `GET /api/v1/apps/list/` request with optional `filter_status`, `page` (default 1), and `size` (default 20) query parameters. It shall return only apps owned by the authenticated user. It shall apply the status filter only for valid `AppStatus` values.

**FR-APP-03 — Get App Detail**
The system shall accept a `GET /api/v1/apps/{id}` request and return all fields of the app record. It shall return HTTP 404 if the app does not exist and HTTP 403 if the app belongs to a different user.

**FR-APP-04 — Delete App**
The system shall accept a `DELETE /api/v1/apps/delete/{id}` request and:
- Verify ownership (HTTP 403 otherwise).
- Stop and remove the Docker container if running (`docker rm -f`).
- Remove the Docker image (`docker rmi -f`).
- Delete the cloned code directory (`BASE_APPS_DIR/app-{id}`).
- Delete the log directory (`BASE_LOGS_DIR/app-{id}`).
- Remove the Nginx config file if `NGINX_ENABLED=true`.
- Delete the database record.
- Return HTTP 204.

**FR-APP-05 — Deploy App**
The system shall accept a `POST /api/v1/apps/{id}/deploy` request and execute the deployment pipeline:

1. Verify ownership.
2. Apply any overrides from the request body (`branch`, `dockerfile_path`, `source_dir`, `env`).
3. If `force_rebuild=true`, delete the app directory before cloning.
4. Clone the repository if the `.git` directory does not exist; otherwise `git pull`.
5. Write env vars to `{app_dir}/.env` if provided.
6. Set app `status=prepared` and commit.
7. Switch to the configured branch.
8. Verify the Dockerfile exists at `dockerfile_path`.
9. Build a Docker image tagged `app_{id}_image:{unix_timestamp}` and `app_{id}_image:latest`, streaming build output to the logger.
10. If a previous container exists, stop and remove it; set `internal_port=null` and commit.
11. Allocate a free host port in range 10000–65535 (DB + OS socket check).
12. Run the container detached with port mapping, resource limits, restart policy, and log rotation.
13. Set app `status=running` and commit.
14. Write the Nginx config file if `NGINX_ENABLED=true`.
15. On any exception: set `status=error`, commit, and re-raise.

**FR-APP-06 — Port Allocation**
The port allocator shall iterate ports from 10000 to 65535. For each port it shall:
- Skip ports already assigned to another app in the database.
- Attempt to bind `0.0.0.0:{port}` with a TCP socket; skip if `OSError` is raised.
- Return the first port that passes both checks.
- Raise `NoAvailablePortError` (error code 2006) if no port is found.

### 3.3 Admin Module

**FR-ADMIN-01 — Health**
`GET /api/v1/admin/health` shall return system metrics (CPU, memory, disk, network, uptime) and database aggregates (total apps, running apps, error apps, total users).

**FR-ADMIN-02 — List All Apps**
`GET /api/v1/admin/apps` shall return a paginated list of all apps from all users, including `user_id` on each item.

**FR-ADMIN-03 — Update Any App**
`PATCH /api/v1/admin/apps/{id}` shall allow updating `status` and `branch` of any app. Invalid status values shall be silently ignored.

**FR-ADMIN-04 — Delete Any App**
`DELETE /api/v1/admin/apps/{id}` shall perform the same full resource cleanup as FR-APP-04 but without ownership restriction.

**FR-ADMIN-05 — List All Users**
`GET /api/v1/admin/users` shall return a paginated list of all user accounts.

**FR-ADMIN-06 — Update Any User**
`PATCH /api/v1/admin/users/{id}` shall allow updating `role` and `billing_type` of any user.

**FR-ADMIN-07 — Delete Any User**
`DELETE /api/v1/admin/users/{id}` shall delete the user and cascade-delete all their apps with full Docker and filesystem cleanup.

**FR-ADMIN-08 — Error Log**
`GET /api/v1/admin/errors` shall return a paginated list of `ErrorLog` records ordered by `id` descending.

### 3.4 Secret Manager Sidecar Module

**FR-SIDECAR-01 — Store Secrets**
`POST /secrets/{app_id}` shall accept a JSON body `{"secrets": {"KEY": "VALUE", ...}}`, serialize the dict to JSON, encrypt with Fernet using `SIDECAR_ENCRYPTION_KEY`, and upsert into the `secret_store` table.

**FR-SIDECAR-02 — Retrieve Secrets**
`GET /secrets/{app_id}` shall retrieve the encrypted record, decrypt it, parse the JSON, and return `{"app_id": N, "secrets": {...}}`. It shall return HTTP 404 if no record exists and HTTP 500 if decryption fails.

**FR-SIDECAR-03 — Delete Secrets**
`DELETE /secrets/{app_id}` shall remove the secret record for the given app.

**FR-SIDECAR-04 — List Secret App IDs**
`GET /secrets` shall return a list of all app IDs that have secrets stored.

**FR-SIDECAR-05 — Key Rotation**
`POST /admin/rotate-key` shall accept `{"new_key": "..."}`, iterate every record in the `secret_store` table, decrypt each with the current key, re-encrypt with the new key, persist to the database, and switch the in-memory key. Failures on individual records shall be logged but shall not abort the rotation of other records.

**FR-SIDECAR-06 — API Key Authentication**
All sidecar endpoints (except `/health`) shall require an `X-Api-Key` header matching `SIDECAR_API_KEY`. Requests with a missing or invalid key shall be rejected with HTTP 403.

### 3.5 Error System

**FR-ERR-01 — Error Code Ranges**
Custom exceptions shall use numeric codes in these ranges:
- 1000–1099: Git / Repository validation errors
- 2000–2099: Docker errors
- 3000–3099: App / Route-level errors
- 4000–4099: Database / Infrastructure errors
- 5000–5099: Internal / Catch-all errors

**FR-ERR-02 — Database Logging**
The exception handler (`exception_handler.py`) shall write every `AppBaseError` to the `error_logs` table with `error_code`, `status_code`, `app_id` (if resolvable from context), and `context` string.

**FR-ERR-03 — Consistent HTTP Response**
The exception handler shall return HTTP responses with a JSON body of `{"error_code": int, "status_code": int, "message": string}` for every `AppBaseError` subclass.

---

## 4. Non-Functional Requirements

### 4.1 Performance

**NFR-PERF-01** — API response time for read endpoints (list apps, get app, auth/me) shall be under 100 ms at p95 for a database containing up to 1000 apps and 500 users on commodity hardware.

**NFR-PERF-02** — Deployment operations (git clone, docker build, docker run) are I/O and CPU bound. They shall not block the FastAPI event loop; all blocking calls shall be dispatched to `asyncio.to_thread`.

**NFR-PERF-03** — Port allocation shall complete in under 50 ms for a system with fewer than 10 000 allocated ports.

### 4.2 Security

**NFR-SEC-01** — Passwords shall be hashed with bcrypt (minimum cost factor 12) before storage. Plaintext passwords shall never be logged or persisted.

**NFR-SEC-02** — JWT secrets (`JWT_SECRET`) shall not default to a static value in production. If not set, the system shall generate a random secret per process, which means tokens are invalidated on restart — this is acceptable for development but is logged as a warning.

**NFR-SEC-03** — Refresh tokens shall be stored only in HttpOnly cookies. Access tokens shall be transmitted only in Authorization headers (never in cookies).

**NFR-SEC-04** — Secrets stored in the sidecar shall be encrypted at rest using Fernet. The encryption key shall never be stored in the same database as the ciphertext.

**NFR-SEC-05** — CORS shall be configured with an explicit allowlist (`CORS_ORIGINS`); `allow_origins=["*"]` is not permitted in production.

**NFR-SEC-06** — Container resource limits (memory 512 MB, CPU 1.0 core by default) shall be applied to every container started by gitDeploy to prevent resource exhaustion on the host.

**NFR-SEC-07** — Admin endpoints shall require `role=admin` enforced at the FastAPI dependency level, not merely by convention.

### 4.3 Reliability

**NFR-REL-01** — If a deployment fails at any stage (git, docker build, docker run), the app status shall be set to `error` and the exception shall be logged before being re-raised.

**NFR-REL-02** — Redis failure (connection refused, timeout) shall not abort any API request. All Redis operations shall be wrapped in try/except with silent fallback.

**NFR-REL-03** — Nginx configuration failure shall not abort a deployment. The Nginx manager catches all exceptions and logs a warning.

**NFR-REL-04** — Sidecar key rotation shall be atomic per record. A failure on one record shall not prevent rotation of the remaining records.

### 4.4 Scalability

**NFR-SCALE-01** — The system shall support up to 55 535 simultaneously deployed apps (one per port in the 10000–65535 range) on a single host, subject to hardware limits.

**NFR-SCALE-02** — Multiple API workers can be run (`uvicorn --workers N`) when using PostgreSQL as the database. SQLite does not support multi-writer concurrency.

**NFR-SCALE-03** — Database schema changes shall be managed through Alembic migrations to support seamless upgrades.

### 4.5 Maintainability

**NFR-MAINT-01** — All application configuration shall be read from environment variables via `Config` class. No configuration values shall be hardcoded in service or route modules.

**NFR-MAINT-02** — All new error types shall be added as `AppBaseError` subclasses with a unique error code in the appropriate range.

**NFR-MAINT-03** — Structured logging shall be used throughout (`logging.getLogger(__name__)`). Log lines shall include timestamp, level, logger name, and message.

### 4.6 Portability

**NFR-PORT-01** — The system shall run on any POSIX-compatible Linux distribution where Python 3.12+, Docker, and Git are available.

**NFR-PORT-02** — The database backend shall be switchable between SQLite and PostgreSQL by changing `DB_URL` without modifying application code.

---

## 5. System Constraints

**SC-01** — Only public GitHub repositories are supported. Private repositories require OAuth tokens which are not implemented in this version.

**SC-02** — Git and Docker must be installed as system binaries accessible on PATH by the user running the API process.

**SC-03** — The system requires outbound HTTPS access to `api.github.com` on port 443 for repository validation. Deployments fail if this endpoint is unreachable.

**SC-04** — Nginx subdomain routing requires wildcard DNS (`*.yourdomain.com → server_ip`) to be configured externally (in DNS provider or Cloudflare).

**SC-05** — The sidecar service uses a separate SQLite database. In a multi-process deployment, the sidecar must run as a single process to avoid SQLite write contention.

**SC-06** — Container log rotation defaults are `--log-opt max-size=10m --log-opt max-file=3`. These are applied at container start time and cannot be changed without recreating the container.

---

## 6. External Interface Requirements

### 6.1 User Interfaces

The React 19 frontend is specified in `docs/FRONTEND_SPEC.md`. Key UI requirements:

- The dashboard shall show all user apps with their current status in real time (polling or WebSocket).
- The deploy form shall accept GitHub URL, container port, branch, Dockerfile path, source directory, and env vars.
- The admin panel shall be accessible only to users with `role=admin` and shall display all tables defined in Section 3.3.
- The UI shall automatically refresh access tokens using the refresh cookie before expiry.

### 6.2 REST API Interface

All endpoints accept and return `application/json`. Authentication is via `Authorization: Bearer <access_token>` header except for public auth endpoints and cookie-driven refresh.

Full endpoint reference is in the README.md API Overview table and in the Swagger UI at `/docs`.

### 6.3 Secret Manager Sidecar Interface

The sidecar exposes a REST API on `SIDECAR_URL` (default `http://localhost:8001`). All non-health endpoints require `X-Api-Key: <SIDECAR_API_KEY>` header. The main API communicates with the sidecar via HTTP; no shared database or IPC.

### 6.4 GitHub API Interface

The system calls `GET https://api.github.com/repos/{owner}/{repo}` with a 5-second timeout to validate each repository URL. The response's `private` field is checked; private repos are rejected with error 1006. Non-200 responses other than 404 raise error 1005.

### 6.5 Docker CLI Interface

Docker operations are performed by spawning subprocess commands:

- `docker build` — with `-t` (two tags), `--label`, `--progress plain`, `-f` (Dockerfile path), optional `--no-cache`, optional `--build-arg`
- `docker run` — with `-d`, `--name`, `-p`, `--restart`, `--memory`, `--cpus`, `--log-driver json-file`, `--log-opt`, optional `-e`
- `docker rm -f` — remove container by ID
- `docker rmi -f` — remove image by ID
- `docker ps -a -q -f name=` — check if a container exists
- `docker images -q` — check if an image exists

### 6.6 Nginx Interface

When `NGINX_ENABLED=true`, the system writes files to `NGINX_CONF_DIR` (default `/etc/nginx/gitdeploy.d`). The main Nginx config must contain an `include /etc/nginx/gitdeploy.d/*.conf;` directive. When `NGINX_AUTO_RELOAD=true`, `nginx -s reload` is executed via subprocess after each write or remove.

### 6.7 Redis Interface

Redis is accessed via the `redis.asyncio` client. The connection is initialised by `init_redis(url)` during application startup. All keys are namespaced under `gitdeploy:`. The interface exposes four operations: `redis_get`, `redis_set`, `redis_delete`, and `redis_incr`.
