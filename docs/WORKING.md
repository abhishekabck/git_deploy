# How gitDeploy Works — Deep Dive

This document explains the internal mechanics of every major subsystem. It is intended for developers and administrators who want to understand exactly what the system does at each step.

---

## 1. End-to-End Deployment Flow

A deployment passes through eight sequential stages. Each stage is atomic: failure at any stage sets `status=error` on the app record, commits the error state to the database, and re-raises the exception to the caller.

### Stage 0 — Request Entry

The client sends `POST /api/v1/apps/{id}/deploy` with an optional request body:
```json
{
  "branch": "feature/my-branch",
  "dockerfile_path": "docker/Dockerfile.prod",
  "source_dir": "backend/",
  "env": {"NODE_ENV": "production"},
  "build_args": {"BUILD_VERSION": "1.2.0"},
  "force_rebuild": false,
  "clear_cache": false
}
```

FastAPI's dependency injector resolves the `AsyncSession` from the connection pool and validates the Bearer token via `get_current_user`.

### Stage 1 — Load and Authorize

`_get_owned_app(app_id, user, db)` executes:
```sql
SELECT * FROM apps WHERE id = :app_id
```
If the row is absent, `AppNotFoundError` (3000) is raised. If `app.user_id != current_user.id`, HTTP 403 is returned. Any request-body overrides (`branch`, `dockerfile_path`, `source_dir`, `env`) are applied to the in-memory model.

### Stage 2 — Prepare Filesystem

The app directory is `BASE_APPS_DIR/app-{id}` (default `/opt/apps/app-{id}`).

If `force_rebuild=true`, the directory tree is deleted synchronously via `asyncio.to_thread(shutil.rmtree, app_dir)`. The directory is then (re)created with `app_dir.mkdir(parents=True, exist_ok=True)`.

### Stage 3 — Git Clone or Pull

`clone_or_pull_repo(repo_url, app_dir, env=props.env)` is called in `asyncio.to_thread`.

It first calls `validate_github_repo(repo_url)`:
- URL must start with `https://github.com/`
- Path must be exactly two segments (`owner/repo` or `owner/repo.git`)
- A `GET https://api.github.com/repos/{owner}/{repo}` request with a 5-second timeout checks that the repo exists and has `private=false`

Then:
- If `app_dir/.git` does not exist: `git clone {repo_url} .` is run in `app_dir`
- If `.git` exists: `git pull` is run in `app_dir`

If `env` is provided, it is written to `app_dir/.env` as `KEY=VALUE` lines.

On success: `app.status = AppStatus.PREPARED`, then `db.commit()`.

### Stage 4 — Docker Build

`docker_build(app, app_dir, build_args=..., clear_cache=...)` is called in `asyncio.to_thread`.

Internally:
1. `switch_to_branch(branch, app_dir)` runs `git checkout {branch}` in the app directory.
2. The Dockerfile path is resolved to `app_dir / app.dockerfile_path`. If the file does not exist, `DockerfileNotFoundError` (2000) is raised.
3. `DockerCommandBuilder` constructs the `docker build` command:
   - `-t app_{id}_image:{unix_timestamp}` (versioned tag)
   - `-t app_{id}_image:latest`
   - `--label app_id={id}`
   - `--label branch={branch}`
   - `--label build_timestamp={ts}`
   - `--progress plain` (non-interactive output)
   - `-f {dockerfile_path}`
   - `--no-cache` if `clear_cache=true`
   - `--build-arg KEY=VALUE` for each entry in `build_args`
   - Build context path (`.` or `source_dir`)
4. `subprocess.Popen` launches the build. The parent process reads `stdout` line by line and forwards each line to the logger — this provides streaming build output without buffering the entire log in memory.
5. `process.wait()` blocks (inside `to_thread`) until the build exits.
6. Non-zero exit code raises `DockerBuildError` (2002).

### Stage 5 — Container Cleanup

Before running a new container, any existing container for this app is removed:
1. `docker_container_exists("app_{id}_container")` runs `docker ps -a -q -f name=app_{id}_container`.
2. If a container ID is returned, `docker_remove_container(name, container_id)` runs `docker rm -f {container_id}`.
3. `app.internal_port = None` is set and committed — this ensures no stale port is associated with the app during the brief window before the new container is assigned a port.

### Stage 6 — Port Allocation

`allocate_free_port(db)` is the async port allocator:

```
1. SELECT internal_port FROM apps WHERE internal_port IS NOT NULL
   → builds a set of used_ports already tracked in the DB

2. For each port in range(10000, 65536):
   a. if port in used_ports → skip
   b. asyncio.to_thread(_is_port_free, port)
      → _is_port_free creates socket.socket(AF_INET, SOCK_STREAM)
        and calls sock.bind(("0.0.0.0", port))
        Returns True if bind succeeds, False if OSError
   c. If port is free → return it

3. If no port found → raise NoAvailablePortError (2006)
```

The two-step check prevents collisions with:
- Other gitDeploy apps (DB check)
- System services, non-gitDeploy Docker containers, and other processes (socket check)

### Stage 7 — Docker Run

`docker_run(app, app_dir, env_vars=...)` is called in `asyncio.to_thread`.

`DockerCommandBuilder` constructs the `docker run` command:
- `-d` — detached
- `--name app_{id}_container`
- `-p {internal_port}:{container_port}` — maps the allocated host port to the app's exposed port
- `--restart unless-stopped`
- `--memory 512m --cpus 1.0` — resource limits
- `--log-driver json-file --log-opt max-size=10m --log-opt max-file=3` — log rotation
- `-e KEY=VALUE` for each env var
- Image: `app_{id}_image:latest`

`subprocess.run` executes the command (not Popen — `docker run -d` returns the container ID immediately without streaming).

On success: `app.status = AppStatus.RUNNING`, `db.commit()`.

### Stage 8 — Nginx Config

`write_app_conf(app.id, app.subdomain, app.internal_port)` is called. If `NGINX_ENABLED=false`, this is a no-op.

When enabled, the function writes:
```
/etc/nginx/gitdeploy.d/app-{id}.conf
```
with a server block that proxies `{subdomain}.{APP_DOMAIN}:80` to `127.0.0.1:{internal_port}`.

If `NGINX_AUTO_RELOAD=true`, `nginx -s reload` is run via subprocess. Failure at this stage is logged as a warning but does not raise an exception — the container is already running successfully.

---

## 2. Port Allocation Algorithm

```
Input: current database rows, OS socket state
Output: a port number in [10000, 65535] not used by anything

1. query = SELECT internal_port FROM apps WHERE internal_port IS NOT NULL
   used_ports = {row[0] for row in result.all()}

2. for port in range(10000, 65536):
       if port in used_ports:
           continue
       free = await asyncio.to_thread(_is_port_free, port)
       if free:
           return port

3. raise NoAvailablePortError
```

`_is_port_free` creates a fresh TCP socket on each call:
```python
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
```

The socket is closed when the `with` block exits — there is no race-free way to reserve the port before Docker uses it, but the window is small because the port is inserted into the database immediately after allocation and the Docker run command follows in the same request.

---

## 3. JWT Token Refresh Flow

Access tokens expire every 15 minutes (configurable). The frontend is expected to refresh silently:

```
1. User sends request with expired access token
   → FastAPI returns HTTP 401

2. Frontend intercepts 401
   → POST /api/v1/auth/refresh (no body required)
   → Browser sends refresh_token cookie automatically
      (HttpOnly, SameSite=Lax, path=/api/v1/auth/refresh)

3. Server reads request.cookies["refresh_token"]
   → decode_token(token) verifies HS256 signature and expiry
   → verifies payload["type"] == "refresh"
   → SELECT user WHERE id = payload["sub"]
   → create_access_token({sub, username, role})
   → returns {"access_token": "...", "token_type": "bearer"}

4. Frontend stores the new access_token in memory (not localStorage)
   → retries the original request

5. If refresh token is also expired:
   → server returns HTTP 401
   → frontend redirects to /login
```

Key security properties:
- The refresh token is in an HttpOnly cookie — JavaScript cannot read it, preventing XSS token theft.
- `SameSite=Lax` prevents the cookie from being sent on cross-site form posts (CSRF protection).
- The cookie is scoped to `path=/api/v1/auth/refresh` — it is never sent on API calls for app data.
- Logout calls `DELETE /api/v1/auth/logout` which returns `Set-Cookie: max_age=0` to expire the cookie server-side, regardless of the client's clock.

---

## 4. Docker Build Process — Detail

The `DockerCommandBuilder` class implements a fluent builder pattern. A typical build call compiles to:

```bash
docker build \
  -t app_1_image:1742567890 \
  -t app_1_image:latest \
  --label app_id=1 \
  --label branch=main \
  --label build_timestamp=1742567890 \
  --progress plain \
  -f /opt/apps/app-1/Dockerfile \
  .
```

Each method on `DockerCommandBuilder` appends to an internal list of strings. `compile()` returns the complete list, which is passed directly to `subprocess.Popen(args=...)`. This avoids shell injection: no string is ever passed through a shell interpreter.

Build output is streamed:
```python
process = subprocess.Popen(args=cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in process.stdout:
    logger.info(line.rstrip())
exit_code = process.wait()
```

`stderr=subprocess.STDOUT` merges stderr into stdout so all build output (including errors) appears in the log stream. The loop reads one line at a time — memory usage is bounded to a single line regardless of image size.

---

## 5. Nginx Routing

The Nginx routing model follows the pattern:

```
Internet → Cloudflare Edge (HTTPS :443) → Cloudflare Tunnel → Nginx :80 → Docker container :internal_port
```

For each deployed app, gitDeploy writes:
```nginx
# /etc/nginx/gitdeploy.d/app-1.conf
server {
    listen 80;
    server_name app-1.yourdomain.com;

    location / {
        proxy_pass         http://127.0.0.1:10000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
```

The `Upgrade` and `Connection` headers support WebSocket connections. `proxy_read_timeout 300s` accommodates long-running server-sent events or streaming responses.

The master Nginx config must include:
```nginx
include /etc/nginx/gitdeploy.d/*.conf;
```

When an app is deleted, `remove_app_conf(app_id)` deletes the file and (if `NGINX_AUTO_RELOAD=true`) runs `nginx -s reload`.

---

## 6. Cloudflare Tunnel Routing

Cloudflare Tunnels expose the server without opening inbound ports. Traffic flow:

```
User browser
  ↓  HTTPS request to app-1.yourdomain.com
Cloudflare Edge (globally distributed)
  ↓  Tunnel connection (initiated outbound from the server)
cloudflared process on the host
  ↓  forwards to localhost:80
Nginx
  ↓  matches server_name app-1.yourdomain.com
  ↓  proxy_pass to 127.0.0.1:10000
Docker container app_1_container
```

The tunnel configuration (`~/.cloudflared/config.yml`) must include a wildcard ingress rule:
```yaml
ingress:
  - hostname: "*.yourdomain.com"
    service: http://localhost:80
  - service: http_status:404
```

DNS records in Cloudflare must have `*.yourdomain.com` pointing to the tunnel (a CNAME to `{tunnel-uuid}.cfargotunnel.com`).

The `scripts/setup_cloudflare_tunnel.sh` script writes this config. The `scripts/add_app_to_tunnel.sh` script adds app-specific routing rules if per-app granularity is desired.

---

## 7. Secret Sidecar Integration

The sidecar is a completely independent FastAPI process. Communication between the main API and the sidecar is over HTTP using a shared API key.

### Encryption

`sidecar/crypto.py` wraps `cryptography.fernet.Fernet`:
- `generate_key()` returns a base64-encoded 32-byte random key
- `encrypt(plaintext, key)` produces a Fernet token (includes version, timestamp, IV, ciphertext, HMAC)
- `decrypt(ciphertext, key)` verifies the HMAC and decrypts; raises `ValueError` if the token is invalid or the key is wrong

### Storage flow for one app

```
main API                sidecar :8001             sidecar DB
    |                        |                         |
    |── POST /secrets/1 ────>|                         |
    |  X-Api-Key: ...         |── verify api key        |
    |  {"secrets":{...}}      |── json.dumps(secrets)   |
    |                         |── Fernet.encrypt(...)   |
    |                         |── UPSERT secret_store ─>|
    |<── {"keys_stored": N} ──|                         |
```

### Key rotation

When `POST /admin/rotate-key` is called with `{"new_key": "..."}`:
1. Every row in `secret_store` is loaded.
2. For each row: decrypt with the old key, re-encrypt with the new key, update in-memory value.
3. `db.commit()` persists all updated rows atomically.
4. `SidecarConfig.ENCRYPTION_KEY` is updated in memory.

If a single row fails to decrypt (corrupted or already on the new key), the error is logged and rotation continues on the remaining rows. This makes key rotation partially fault-tolerant.

### Security hardening checklist

- `SIDECAR_ENCRYPTION_KEY` must be set in the sidecar process environment; if not set, a random key is generated (warning logged) and secrets are unrecoverable after restart.
- `SIDECAR_API_KEY` must match between the main API's `Config.SIDECAR_API_KEY` and the sidecar's `SidecarConfig.API_KEY`.
- The sidecar should not be exposed on a public network interface; bind it to `127.0.0.1:8001`.
- The sidecar's SQLite database file should have restricted file permissions: `chmod 600 secrets.db`.

---

## 8. Error System

### Error code taxonomy

| Range | Domain              | Examples                                                  |
|-------|---------------------|-----------------------------------------------------------|
| 1000–1099 | Git / GitHub    | 1000 invalid URL, 1004 repo not found, 1007 clone failed  |
| 2000–2099 | Docker          | 2000 no Dockerfile, 2002 build failed, 2005 run failed    |
| 3000–3099 | App / Route     | 3000 app not found, 3002 deploy permission denied         |
| 4000–4099 | Database        | 4000 connection failed                                    |
| 5000–5099 | Internal        | 5000 unexpected server error                              |

### Flow from exception to HTTP response

```
Service code raises:  DockerBuildError(detail="...", context="app_1_image")

exception_handler.py:
  1. Receives AppBaseError instance
  2. Calls error_logger.log_error(error, db)
     → INSERT INTO error_logs (error_code, status_code, app_id, context, created_at)
  3. Returns JSONResponse:
     {
       "error_code": 2002,
       "status_code": 500,
       "message": "Docker build failed."
     }
  HTTP status code = error.status_code = 500
```

### Logging

Standard Python `logging` is used throughout. Every module obtains a logger with `logging.getLogger(__name__)`. Log format:
```
2026-03-17 12:34:56,789 | INFO | app.services.docker | Docker build completed for app_1_image
```

This structured format makes grepping by module name straightforward.
