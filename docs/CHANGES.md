# Changelog — gitDeploy

All notable changes are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [2.0.0] — 2026-03-17

This release is a complete architectural overhaul of the v1.0 synchronous prototype. The entire backend has been converted to async, a full admin surface has been added, a companion sidecar service manages encrypted secrets, Redis is available as an optional caching layer, and infrastructure automation scripts cover both Nginx and Cloudflare Tunnel.

---

### Added

#### Authentication system (`api/v1/auth.py`, `app/services/auth.py`)

- JWT-based auth with short-lived access tokens (15-minute default expiry, configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Long-lived refresh tokens (7-day default expiry) stored in HttpOnly, SameSite=Lax cookies scoped to `/api/v1/auth/refresh` to prevent XSS token theft and CSRF abuse simultaneously
- `POST /api/v1/auth/refresh` — silent token renewal: reads the cookie, validates the refresh claim, issues a new access token without requiring credentials
- `POST /api/v1/auth/logout` — server-side cookie expiration (not just a client-side delete)
- `GET /api/v1/auth/me` — returns the authenticated user profile
- Role-based access control: `user` and `admin` roles stored as an Enum column on the `users` table
- Billing tier field on users: `free` and `paid` variants via `BillingType` enum
- `get_admin_user` dependency that guards all admin routes at the dependency-injection level

#### Admin API (`api/v1/admin.py`)

- `GET /api/v1/admin/health` — real-time system metrics (CPU %, memory MB, disk GB, network bytes, uptime seconds) via psutil, plus aggregate DB counts of total/running/error apps and total users
- `GET /api/v1/admin/apps` — paginated list of all apps across all users with optional `filter_status` query parameter
- `PATCH /api/v1/admin/apps/{id}` — admin force-update of any app's `status` or `branch`
- `DELETE /api/v1/admin/apps/{id}` — admin force-delete: stops and removes the container, removes the Docker image, deletes cloned code and log directories, removes Nginx config
- `GET /api/v1/admin/users` — paginated user list ordered by `id` ascending
- `PATCH /api/v1/admin/users/{id}` — update user `role` or `billing_type`
- `DELETE /api/v1/admin/users/{id}` — delete a user account and cascade-delete all their apps with full Docker/filesystem cleanup

#### Error log endpoint (`api/v1/admin.py`)

- `GET /api/v1/admin/errors` — paginated reverse-chronological error log viewer returning `error_code`, `status_code`, `app_id`, `context`, and `created_at` for each event

#### Secret Manager Sidecar (`sidecar/`)

- Companion FastAPI service running on port 8001 with its own async SQLite database (`secrets.db`)
- Per-app secret storage using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256 via the `cryptography` library)
- Authentication via `X-Api-Key` header shared between the main API and the sidecar
- `POST /secrets/{app_id}` — store or overwrite encrypted secrets (accepts `{"secrets": {...}}`)
- `GET /secrets/{app_id}` — retrieve and return decrypted secrets dict
- `DELETE /secrets/{app_id}` — delete all secrets for an app
- `GET /secrets` — list all app IDs that have stored secrets
- `POST /admin/rotate-key` — atomically re-encrypt every stored secret with a new Fernet key; sidecar switches to the new key in memory after the operation completes successfully
- Ephemeral key warning: if `SIDECAR_ENCRYPTION_KEY` is not set, a random key is generated at startup and a warning is logged; secrets will be lost on restart

#### Redis caching service (`app/services/redis_service.py`)

- Optional async Redis integration using `redis.asyncio`
- All keys prefixed with `gitdeploy:` to coexist safely with other Redis tenants on the same instance
- Graceful no-op fallback: if `REDIS_ENABLED=false` or the Redis server is unreachable, every operation silently passes through without raising an exception
- Helpers: `redis_get`, `redis_set` (with TTL), `redis_delete`, `redis_incr` (with auto-expiry for rate-limiting counters)
- Initialised during FastAPI `lifespan` startup; connection closed cleanly on shutdown

#### System metrics service (`app/services/system_metrics.py`)

- `get_system_metrics()` async function wrapping `psutil` calls in `asyncio.to_thread`
- Reports: CPU percentage (0.5-second sample interval), CPU core count, memory total/available/used/percent, disk total/free/used/percent, network bytes sent/received, process uptime in seconds

#### Nginx manager service (`app/services/nginx_manager.py`)

- Automatically writes per-app Nginx server block to `NGINX_CONF_DIR/app-{id}.conf` on every successful deployment
- Automatically removes the file on app delete or admin delete
- Template proxies `{subdomain}.{domain}:80` to `127.0.0.1:{internal_port}` with WebSocket upgrade support and appropriate proxy headers
- `NGINX_AUTO_RELOAD=true` triggers `nginx -s reload` after each write or remove; failure is logged as a warning and does not abort the deployment
- All file operations run in `asyncio.to_thread`; errors are caught and logged, never raised — a missing Nginx binary does not break a deployment

#### Infrastructure scripts (`scripts/`)

- `setup_nginx.sh` — creates `/etc/nginx/gitdeploy.d/` and writes the master `include` directive into the default Nginx config
- `add_app_to_nginx.sh` — manually generates and symlinks a per-app server block
- `remove_app_from_nginx.sh` — removes a per-app server block and reloads Nginx
- `setup_cloudflare_tunnel.sh` — writes `~/.cloudflared/config.yml` with wildcard subdomain ingress rules
- `add_app_to_tunnel.sh` — adds a single app subdomain routing rule to the tunnel config
- `generate_nginx_conf.py` — Python helper that renders the Nginx config Jinja2 template

#### Database migrations (`migrations/`)

- Alembic integration: `alembic.ini` at the project root, `migrations/env.py` using async engine
- Initial migration creating `users`, `apps`, and `error_logs` tables with all v2.0 columns

#### Documentation (`docs/`)

- `ARCHITECTURE.md` — layered architecture with ASCII diagrams and deployment topology
- `WORKING.md` — end-to-end deep dive for every subsystem
- `SRS.md` — formal Software Requirements Specification
- `UML.md` — class, sequence, state, and component diagrams (ASCII)
- `DFD.md` — Data Flow Diagrams Level 0, 1, and 2 (ASCII)
- `ADMIN_GUIDE.md` — administrator operations guide
- `CHANGES.md` — this file
- `CLOUDFLARE_SETUP.md` — Cloudflare Tunnel configuration walkthrough
- `SIDECAR_SETUP.md` — secret manager setup, key generation, systemd service unit
- `FRONTEND_SPEC.md` — full API contract specification for UI developers
- `NGINX_STEPS.md` — Nginx reverse proxy setup guide
- `RESUME_DESCRIPTION.md` — portfolio project description

---

### Changed

#### Architecture — full async conversion

- All database queries converted from synchronous SQLAlchemy ORM to SQLAlchemy 2.0 `AsyncSession` with `async_sessionmaker`
- Engine changed from `create_engine` to `create_async_engine`; SQLite driver switched from `pysqlite` to `aiosqlite`, PostgreSQL driver switched from `psycopg2` to `asyncpg`
- All subprocess calls (git, docker) wrapped in `asyncio.to_thread()` to prevent event-loop blocking while still reusing the existing synchronous helper functions
- Database initialisation and Redis initialisation moved into FastAPI `lifespan` async context manager, replacing the deprecated `@app.on_event("startup")` pattern
- Dependency `get_db()` updated to yield an `AsyncSession` and close it with `async with`
- All route handlers converted from `def` to `async def`

#### Models (`app/models/`)

- `users` table: added `role` (Enum), `billing_type` (Enum), `updated_at` (DateTime, server-default `now()`)
- `apps` table: added `dockerfile_path` (String), `build_path` (String), `env` (JSON); renamed `port` to `internal_port` for clarity; `internal_port` is now nullable to support the pre-deployment state; added `branch` (String, default `"main"`)
- `error_logs` table: `created_at` column now uses `lambda: datetime.now(timezone.utc)` to ensure timezone-aware datetime objects on every insert (fixes naive-datetime comparison bug)

#### Services

- `deploy.py`: added `validate_github_repo()` using the GitHub API to confirm a repo is public before cloning; separated `clone_or_pull_repo()` and `switch_to_branch()` into distinct, testable functions; added `force_rebuild` option that deletes the app directory before recloning
- `port_manager.py`: now queries the `apps` table for already-assigned `internal_port` values AND independently checks each candidate port with a raw `socket.bind()` call via `asyncio.to_thread`; the union of both sources guarantees collision-free allocation even against containers started outside gitDeploy
- `auth.py`: fully rewritten to use async DB queries; `create_access_token` and `create_refresh_token` both use `python-jose`; refresh token carries `{"sub": user_id, "type": "refresh"}` claim
- `docker.py` (previously inline in the deploy endpoint): extracted to a dedicated service module; added resource limits (`--memory 512m --cpus 1.0`), Docker labels, and JSON log rotation (`--log-opt max-size=10m,max-file=3`) to the run command
- `docker_command_builder.py` (new): fluent builder pattern for constructing Docker CLI argument lists for both `build` and `run` commands, removing brittle string concatenation

#### API layer

- `api/__init__.py`: router prefix updated from `/api` to `/api/v1`; admin router mounted
- Ownership checks in `apps.py` (`_get_owned_app`) ensure users can only operate on their own apps; 403 returned (not 404) on cross-user access attempts

#### Error system (`app/Errors/`)

- Error codes formalised into numeric ranges: 1xxx Git/Repository, 2xxx Docker, 3xxx App/Route, 4xxx Database/Infrastructure, 5xxx Internal catch-all
- `error_logger.py` writes error records asynchronously to the `error_logs` DB table, including `error_code`, `status_code`, `app_id` (when available), and `context` string
- `exception_handler.py` catches all `AppBaseError` subclasses and returns a consistent `{"error_code": ..., "status_code": ..., "message": ...}` JSON body

#### Configuration (`app/config.py`)

- Added: `REDIS_ENABLED`, `REDIS_URL`, `SIDECAR_URL`, `SIDECAR_API_KEY`, `APP_DOMAIN`, `CORS_ORIGINS`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `NGINX_ENABLED`, `NGINX_CONF_DIR`, `NGINX_AUTO_RELOAD`
- `JWT_SECRET` now defaults to `secrets.token_hex(32)` at import time if not provided in environment (random per process — a warning that a persistent value must be set in production)

---

### Fixed

- **Port collision bug**: the v1.0 allocator only queried the `apps` database table. Containers started outside gitDeploy, or containers left behind by failed deployments, could hold the same port without the allocator knowing. The fix cross-references OS-level socket bindings via `socket.bind()` in addition to the DB query.
- **Session leak**: synchronous SQLAlchemy sessions were not always closed when an exception was raised mid-request. The async `AsyncSession` wrapped in `async with` eliminates the leak.
- **Docker image accumulation**: the v1.0 deploy endpoint did not remove the previous image when redeploying the same app. Over time this filled disk with stale layers. The fix explicitly removes the existing container and image with `docker rm -f` and `docker rmi -f` before rebuilding.
- **CORS wildcard**: hardcoded `allow_origins=["*"]` replaced with the configurable `CORS_ORIGINS` list.
- **Refresh token not invalidated on logout**: in v1.0 only the client-side cookie was removed. The server now explicitly sets `max_age=0` on the `Set-Cookie` response header to expire the cookie at the proxy/browser level.
- **`ErrorLog.created_at` naive datetime**: v1.0 used `default=datetime.utcnow` which produces a timezone-naive object; comparisons with timezone-aware datetimes raised `TypeError`. Fixed by switching to `lambda: datetime.now(timezone.utc)`.
- **`internal_port` NOT NULL constraint**: v1.0 defined `internal_port` as `NOT NULL`, which made it impossible to create an app record before a port was allocated. Changed to `nullable=True`; the column is populated during the deploy pipeline.

---

## [1.0.0] — 2025-11-01

Initial working prototype.

### Added

- FastAPI backend with synchronous SQLAlchemy
- `users` and `apps` database tables
- `POST /api/v1/apps/create` — create app record
- `POST /api/v1/apps/{id}/deploy` — clone GitHub repo, docker build, docker run
- `GET /api/v1/apps/list/` — list user's apps
- `GET /api/v1/apps/{id}` — get app detail
- `DELETE /api/v1/apps/delete/{id}` — delete app and stop container
- Basic JWT login (`POST /login`, `POST /register`)
- Port allocator (database-only check, range 10000–65535)
- Docker automation via subprocess
- Git clone via subprocess
- Deployment status tracking: `created`, `prepared`, `running`, `error`

---

[2.0.0]: https://github.com/yourusername/gitdeploy/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/yourusername/gitdeploy/releases/tag/v1.0.0
