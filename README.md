```
  ___  _ _  ____             _
 / _ \(_) ||  _ \  ___ _ __ | | ___  _   _
| (_) | | || | | |/ _ \ '_ \| |/ _ \| | | |
 \__, | | || |_| |  __/ |_) | | (_) | |_| |
   /_/|_|_||____/ \___| .__/|_|\___/ \__, |
                       |_|            |___/
  Self-hosted PaaS — deploy GitHub repos as Docker containers
```

---

**gitDeploy** is a lightweight, self-hosted Platform as a Service. Point it at any public GitHub repository and it clones the code, builds a Docker image from your Dockerfile, runs the container on a dynamically allocated port, and wires up an Nginx reverse-proxy so the app is reachable at `app-{id}.gitdeploy.online` — all through a single REST API call.

No cloud vendor lock-in. No monthly platform fees. Full control over your infrastructure.

---

## Features

- Deployment from GitHub URL — clone or re-pull, build, and run in one request
- Per-user multi-tenancy with JWT authentication (access token + HttpOnly refresh cookie)
- Admin role with full system control over all apps, users, and error logs
- Async throughout — FastAPI + SQLAlchemy 2.0 async, `asyncio.to_thread` for Docker and Git
- Automatic port allocation in range 10000-65535, verified against both the DB and the OS socket layer
- Docker build with live log streaming, Unix-timestamp-tagged images, and optional `--no-cache`
- Branch switching, custom Dockerfile paths, build args, and env-var injection at deploy time
- Nginx per-app server block auto-generation and hot-reload on deploy and delete
- Cloudflare Tunnel integration scripts for zero-open-port public access
- Optional Redis caching layer under the `gitdeploy:` namespace (graceful no-op if absent or unreachable)
- Secret Manager Sidecar — companion FastAPI service storing per-app env vars encrypted with Fernet (AES-128-CBC + HMAC-SHA256)
- Structured error system with numeric codes (1xxx=git, 2xxx=docker, 3xxx=app, 4xxx=db, 5xxx=internal) and database-backed error logging
- System health endpoint reporting CPU, memory, disk, network, and app/user statistics via psutil
- SQLite default (zero-config) with drop-in PostgreSQL support via asyncpg
- Alembic migrations included

---

## Architecture

```
                    ┌──────────────────────┐
                    │   React 19 Frontend   │
                    │  Vite · Tailwind CSS  │
                    │  TanStack Query v5    │
                    │  Zustand · RR v7      │
                    └──────────┬───────────┘
                               │  HTTP / JSON (port 5173 dev)
              ┌────────────────▼────────────────────────┐
              │           FastAPI  v1.0.0  :8082          │
              │  /api/v1/auth    /api/v1/apps             │
              │  /api/v1/admin   /  (health)              │
              └────┬──────────────┬──────────────┬───────┘
                   │              │              │
        ┌──────────▼───┐  ┌───────▼──────┐  ┌───▼────────────┐
        │ Auth Service  │  │Deploy Service│  │ Admin Service   │
        │ JWT sign/     │  │ Git + Docker │  │ Health/Users/   │
        │ verify/       │  │ Port alloc   │  │ Apps/Errors     │
        │ bcrypt        │  │ Nginx mgr    │  │ psutil metrics  │
        └───────────────┘  └──────┬───────┘  └────────────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               │                  │                  │
      ┌────────▼──────┐  ┌────────▼──────┐  ┌────────▼────────┐
      │   Git CLI      │  │  Docker CLI   │  │  Port Manager   │
      │  clone/pull    │  │  build / run  │  │  10000-65535    │
      │  branch switch │  │  rm container │  │  DB + OS check  │
      └───────────────-┘  └───────────────┘  └─────────────────┘
               │
      ┌────────▼──────────────────────────────────────────────-┐
      │                       Data Layer                         │
      │  SQLAlchemy 2.0 async   SQLite (default) / PostgreSQL   │
      │  Redis optional (gitdeploy: namespace)                   │
      │  Alembic migrations                                      │
      └──────────────────────────────────────────────────────────┘
               │
      ┌────────▼──────────────────────────────────────────────-┐
      │                    Infrastructure                        │
      │  Docker Engine                                           │
      │  Nginx  (per-app server blocks in /etc/nginx/gitdeploy.d)│
      │  Cloudflare Tunnel  (optional, no open inbound ports)   │
      │  Secret Manager Sidecar  :8001  (Fernet encryption)     │
      └──────────────────────────────────────────────────────────┘
```

---

## Prerequisites

Before running gitDeploy, ensure the following are installed and configured on your system:

| Requirement | Purpose | Install |
|-------------|---------|---------|
| **Python 3.11+** | Backend runtime | `apt install python3 python3-venv python3-pip` |
| **Docker Engine** | Build and run deployed apps | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| **Git** | Clone user repositories | `apt install git` |
| **Nginx** | Subdomain reverse-proxy routing | `apt install nginx` |
| **PostgreSQL** (recommended) | Production database | `apt install postgresql` or use Docker |
| **Cloudflare account + `cloudflared`** | Public tunnel access (no open ports) | [developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) |
| **A domain name** | For `app-{id}.yourdomain.com` routing | Any registrar; NS pointed to Cloudflare |
| **Node.js 18+** (frontend only) | Build the React UI | `apt install nodejs npm` or use nvm |

**System requirements:** Linux server (Debian/Ubuntu recommended), 2+ GB RAM, root or sudo access for Nginx/Docker.

---

## Quick Start

**Step 1 — Clone and install**
```bash
git clone https://github.com/yourname/gitDeploy.git
cd gitDeploy
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Step 2 — Configure environment**
```bash
# Copy the example (create .env.example if needed) or create .env directly
cat > .env << 'EOF'
DB_URL=sqlite+aiosqlite:///./gitdeploy.db
JWT_SECRET=change-this-to-a-long-random-string
BASE_APPS_DIR=/opt/apps
BASE_LOGS_DIR=/opt/logs
APP_DOMAIN=localhost
CORS_ORIGINS=http://localhost:5173
EOF
```

**Step 3 — Run database migrations**
```bash
alembic upgrade head
```

**Step 4 — Start the API server**
```bash
uvicorn main:app --host 0.0.0.0 --port 8082 --reload
```

**Step 5 — Register, create, and deploy your first app**
```bash
# Register a user
curl -s -X POST http://localhost:8082/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"secret123"}'

# Login and capture the token
TOKEN=$(curl -s -X POST http://localhost:8082/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"secret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create an app record
curl -s -X POST http://localhost:8082/api/v1/apps/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"hello-world","repo_url":"https://github.com/owner/repo","container_port":3000}'

# Deploy it (clone + build + run)
curl -s -X POST http://localhost:8082/api/v1/apps/1/deploy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

The app is now running. With Nginx enabled and `APP_DOMAIN` set, it is reachable at `http://app-1.yourdomain.com`.

---

## API Overview

### Authentication — `/api/v1/auth`

| Method | Endpoint    | Description                              | Auth           |
|--------|-------------|------------------------------------------|----------------|
| POST   | /register   | Create a new user account                | Public         |
| POST   | /login      | Authenticate; returns access token + sets HttpOnly refresh cookie | Public |
| POST   | /refresh    | Issue new access token using refresh cookie | Cookie only |
| POST   | /logout     | Clear the refresh-token cookie           | Public         |
| GET    | /me         | Return the currently authenticated user  | Bearer token   |

### Apps — `/api/v1/apps`

| Method | Endpoint          | Description                                         | Auth         |
|--------|-------------------|-----------------------------------------------------|--------------|
| POST   | /create           | Register a new app (validate repo, save to DB)      | Bearer token |
| GET    | /list/            | List your apps (filter by status, paginated)        | Bearer token |
| GET    | /{id}             | Get full app detail including port and status       | Bearer token |
| DELETE | /delete/{id}      | Delete app record, container, image, and filesystem | Bearer token |
| POST   | /{id}/deploy      | Full deploy pipeline: git + docker build + run      | Bearer token |

### Admin — `/api/v1/admin`

| Method | Endpoint        | Description                                     | Auth       |
|--------|-----------------|-------------------------------------------------|------------|
| GET    | /health         | System metrics (CPU/mem/disk) + app/user stats  | Admin role |
| GET    | /apps           | List all apps across all users (paginated)      | Admin role |
| PATCH  | /apps/{id}      | Update any app's status or branch               | Admin role |
| DELETE | /apps/{id}      | Force-delete any app and its resources          | Admin role |
| GET    | /users          | List all users (paginated)                      | Admin role |
| PATCH  | /users/{id}     | Change user role or billing tier                | Admin role |
| DELETE | /users/{id}     | Delete user and cascade-delete all their apps   | Admin role |
| GET    | /errors         | Paginated error log from the database           | Admin role |

Interactive docs are available at `http://localhost:8082/docs` (Swagger UI) and `http://localhost:8082/redoc`.

---

## Admin Dashboard Features

The React admin panel (accessed at `/admin` in the frontend) provides:

- **System health panel** — live CPU %, memory used/total (MB), disk used/free (GB), network bytes sent/received, process uptime in seconds, total/running/error app counts and total user count
- **App manager** — paginated table of all apps across all users with inline status editing and force-delete
- **User manager** — list all users, promote to admin, change billing tier (free/paid), delete with full cascade cleanup of containers, images, and filesystem directories
- **Error log viewer** — reverse-chronological paginated table with error code, HTTP status, app ID, context string, and timestamp

---

## Environment Variables

| Variable                        | Default                                        | Description                                        |
|---------------------------------|------------------------------------------------|----------------------------------------------------|
| `DB_URL`                        | `sqlite+aiosqlite:///./gitdeploy.db`           | SQLAlchemy async database URL                      |
| `BASE_APPS_DIR`                 | `/opt/apps`                                    | Root directory where cloned repos are stored       |
| `BASE_LOGS_DIR`                 | `/opt/logs`                                    | Root directory for Docker container log files      |
| `JWT_SECRET`                    | random per process start — **always set this** | HMAC-SHA256 secret used to sign JWTs               |
| `ACCESS_TOKEN_EXPIRE_MINUTES`   | `15`                                           | Access token TTL in minutes                        |
| `REFRESH_TOKEN_EXPIRE_DAYS`     | `7`                                            | Refresh token TTL in days                          |
| `APP_DOMAIN`                    | `localhost`                                    | Base domain used to build `app-{id}.APP_DOMAIN`    |
| `CORS_ORIGINS`                  | `http://localhost:5173,http://127.0.0.1:5500`  | Comma-separated allowed CORS origins               |
| `REDIS_ENABLED`                 | `false`                                        | Enable Redis. Set to `true` to activate            |
| `REDIS_URL`                     | `redis://localhost:6379/0`                     | Redis connection URL                               |
| `NGINX_ENABLED`                 | `false`                                        | Auto-write Nginx server blocks on deploy/delete    |
| `NGINX_CONF_DIR`                | `/etc/nginx/gitdeploy.d`                       | Directory for per-app Nginx `.conf` files          |
| `NGINX_AUTO_RELOAD`             | `false`                                        | Run `nginx -s reload` after each config change     |
| `NGINX_LISTEN_PORT`             | `80`                                           | Port used in generated Nginx server blocks         |
| `CF_ZONE_ID`                    | —                                              | Cloudflare Zone ID (for DNS management script)     |
| `CF_API_TOKEN`                  | —                                              | Cloudflare API token with DNS write permission     |
| `CF_TUNNEL_ID`                  | —                                              | Cloudflare Tunnel ID                               |
| `SIDECAR_URL`                   | `http://localhost:8001`                        | URL of the Secret Manager Sidecar                  |
| `SIDECAR_API_KEY`               | random per process start — **always set this** | Shared API key between main app and sidecar        |
| `VALID_API_KEY`                 | `""`                                           | Optional static key for machine-to-machine access  |

---

## Tech Stack

**Backend**
- Python 3.12 / FastAPI 0.123 / Uvicorn / Starlette
- SQLAlchemy 2.0 async / aiosqlite / asyncpg
- Pydantic v2 / python-jose (JWT) / bcrypt / passlib
- Alembic (migrations) / psutil (metrics) / redis (async)
- cryptography — Fernet (sidecar encryption)

**Frontend**
- React 19 / Vite / TypeScript
- Tailwind CSS / shadcn/ui
- TanStack Query v5 / Zustand / React Router v7
- Axios

**Infrastructure**
- Docker Engine (CLI-driven build and run)
- Nginx (optional — per-app server block auto-generation)
- Cloudflare Tunnels (optional — zero open port public access)

---

## Deployment Options

### Local (development only)
```bash
uvicorn main:app --reload --port 8082
```
Apps are accessible on `localhost:<internal_port>`. No subdomain routing.

### With Nginx (production, LAN or server)
```bash
# One-time: run the setup script and set env vars
sudo bash scripts/setup_nginx.sh
```

Set in `.env`:
```env
NGINX_ENABLED=true
NGINX_AUTO_RELOAD=true
APP_DOMAIN=yourdomain.com
```

Each deployed app gets `/etc/nginx/gitdeploy.d/app-{id}.conf` written automatically. The file proxies `app-{id}.yourdomain.com:80` to `127.0.0.1:<internal_port>`.

### With Cloudflare Tunnels (public internet, no open inbound ports)
```bash
bash scripts/setup_cloudflare_tunnel.sh
bash scripts/add_app_to_tunnel.sh app-1 yourdomain.com
```

See `docs/CLOUDFLARE_SETUP.md` for the complete walkthrough including tunnel creation, DNS records, and routing config.

---

## Secret Management

The optional Secret Manager Sidecar (`sidecar/`) is a separate FastAPI process on port 8001. It stores per-app environment secrets encrypted with Fernet (AES-128-CBC + HMAC-SHA256), authenticated via a shared API key.

```bash
# Generate a Fernet encryption key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Start the sidecar
SIDECAR_ENCRYPTION_KEY=<key> SIDECAR_API_KEY=<api_key> python -m sidecar.main

# Store secrets for app ID 1
curl -X POST http://localhost:8001/secrets/1 \
  -H "X-Api-Key: <SIDECAR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"secrets": {"DATABASE_URL": "postgres://...", "API_KEY": "..."}}'

# Retrieve secrets
curl http://localhost:8001/secrets/1 \
  -H "X-Api-Key: <SIDECAR_API_KEY>"

# Rotate the encryption key (re-encrypts all stored secrets in place)
curl -X POST http://localhost:8001/admin/rotate-key \
  -H "X-Api-Key: <SIDECAR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"new_key": "<new_fernet_key>"}'
```

See `docs/SIDECAR_SETUP.md` for the full setup and security hardening guide.

---

## Production with PostgreSQL

```env
DB_URL=postgresql+asyncpg://user:password@localhost:5432/gitdeploy
```

Then run migrations:
```bash
alembic upgrade head
```

For multiple workers:
```bash
uvicorn main:app --host 0.0.0.0 --port 8082 --workers 4
```

Note: with multiple workers, `JWT_SECRET` must be set to a fixed value in `.env` (not auto-generated) so all workers share the same signing key.

---

## Project Structure

```
gitDeploy/
├── main.py                     FastAPI app entry point, lifespan, CORS, router
├── requirements.txt
├── alembic.ini
├── api/
│   └── v1/
│       ├── auth.py             Register, login, refresh, logout, /me
│       ├── apps.py             Create, list, detail, deploy, delete
│       └── admin.py            Health, all apps/users/errors (admin only)
├── app/
│   ├── config.py               All config read from environment variables
│   ├── constants.py            AppStatus, UserRoles, BillingType enums
│   ├── database.py             Async SQLAlchemy engine + session factory
│   ├── dependencies.py         FastAPI dependency injectors (get_db)
│   ├── utils.py                Password hashing helpers
│   ├── models/
│   │   ├── users.py            Users ORM model
│   │   ├── app_model.py        AppModel ORM model
│   │   ├── error_log.py        ErrorLog ORM model
│   │   └── timestatus_mixin.py created_at / updated_at mixin
│   ├── schemas/                Pydantic v2 request and response schemas
│   ├── services/
│   │   ├── auth.py             JWT creation, decoding, get_current_user
│   │   ├── deploy.py           GitHub validation, git clone/pull/branch
│   │   ├── docker.py           docker build / run / rm (CLI subprocess)
│   │   ├── docker_command_builder.py  Builder pattern for Docker CLI args
│   │   ├── port_manager.py     Async port allocator (DB + OS socket check)
│   │   ├── nginx_manager.py    Per-app Nginx config write/remove/reload
│   │   ├── redis_service.py    Async Redis wrapper with gitdeploy: prefix
│   │   └── system_metrics.py  psutil CPU/memory/disk/network collection
│   └── Errors/
│       ├── app_errors.py       All custom exception classes (1xxx-5xxx)
│       ├── error_logger.py     DB writer for error events
│       └── exception_handler.py  FastAPI exception handler for AppBaseError
├── sidecar/                    Secret Manager companion service (port 8001)
│   ├── main.py                 FastAPI app with secrets CRUD + key rotation
│   ├── config.py               Sidecar env config
│   ├── crypto.py               Fernet encrypt/decrypt/generate_key
│   ├── database.py             Separate async DB for secrets
│   ├── models.py               SecretStore ORM model
│   └── dependencies.py         get_db, verify_api_key
├── scripts/
│   ├── setup_nginx.sh          One-time Nginx master config setup
│   ├── add_app_to_nginx.sh     Manually add an app to Nginx
│   ├── remove_app_from_nginx.sh Manually remove an app from Nginx
│   ├── setup_cloudflare_tunnel.sh  Create and configure Cloudflare tunnel
│   ├── add_app_to_tunnel.sh    Add subdomain routing rule to tunnel config
│   ├── cf_dns.sh               Cloudflare DNS record management (setup/list/add/delete)
│   └── generate_nginx_conf.py  Python helper to render Nginx config template
├── migrations/                 Alembic migration scripts
└── docs/                       All documentation files
```

---

## Documentation Index

| Document                       | Contents                                           |
|--------------------------------|----------------------------------------------------|
| `docs/ARCHITECTURE.md`         | Layered architecture and deployment topology       |
| `docs/WORKING.md`              | End-to-end flow explanations for every subsystem   |
| `docs/SRS.md`                  | Software Requirements Specification (formal)       |
| `docs/UML.md`                  | Class, sequence, state, and component diagrams     |
| `docs/DFD.md`                  | Data Flow Diagrams — Level 0, 1, and 2             |
| `docs/ADMIN_GUIDE.md`          | Admin user guide                                   |
| `docs/CHANGES.md`              | Changelog                                          |
| `docs/AUTH_GUIDE.md`           | Authentication deep-dive                           |
| `docs/ERROR_SYSTEM.md`         | Error code reference                               |
| `docs/SIDECAR_SETUP.md`        | Secret Manager Sidecar setup                       |
| `docs/CLOUDFLARE_SETUP.md`     | Cloudflare Tunnel setup                            |
| `docs/NGINX_STEPS.md`          | Nginx manual setup steps                           |
| `docs/FRONTEND_SPEC.md`        | Frontend specification                             |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit with a clear message describing the change
4. Open a pull request against `main`

Code guidelines:
- All new service code must be async or use `asyncio.to_thread` for blocking operations
- Request and response data must use Pydantic v2 models
- Errors must be raised as `AppBaseError` subclasses with an appropriate error code
- All new endpoints must be covered by the existing route prefix structure

---

## License

MIT License — see `LICENSE` for details.
