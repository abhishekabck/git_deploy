# gitDeploy — Next Steps Guide
> Generated: 2026-03-12 | Current completion: ~45%

---

## Architecture Recap

```
Frontend → REST API → FastAPI → Service Layer → Response
                                     │
                               Docker (build + run)
                               Nginx  (subdomain routing)
                               Cloudflare (public tunnel)
```

---

## Part 1 — Bugs & Errors Found in Current Code

These must be fixed before building anything new on top.

---

### BUG 1 — CRITICAL: `user_id` FK breaks every app creation
**File:** `app/models/app_model.py:19`

```python
user_id = Column(ForeignKey("users.id"), nullable=False)
```

`user_id` is `nullable=False` but the `POST /apps/create` endpoint never sets it.
Every single create request will fail with a DB constraint violation right now.

**Fix:** Either make it `nullable=True` temporarily until auth is implemented,
or add a hardcoded default user for dev. This is the most critical blocker.

---

### BUG 2 — `internal_port` not Optional in AppDetail schema
**File:** `app/schemas/app_detail_schema.py:5`

```python
internal_port: int   # ← crashes on newly created (not yet deployed) apps
```

`internal_port` is `None` until deploy happens. So `GET /apps/{id}` on a fresh
app will throw a Pydantic validation error.

**Fix:** Change to `internal_port: int | None = None`

---

### BUG 3 — Wrong default type for `role` in Users model
**File:** `app/models/users.py:16`

```python
role = Column(Enum(UserRoles), nullable=False, default="user")  # ← string, not enum
```

Should be `default=UserRoles.USER`. SQLAlchemy strict enum column expects
the enum instance, not a raw string.

---

### BUG 4 — `ErrorLog.created_at` is a static timestamp (evaluated once at class load)
**File:** `app/models/error_log.py:15`

```python
created_at = Column(DateTime, default=datetime.now(timezone.utc))  # ← runs ONCE
```

`datetime.now()` is called when the class is defined, so every row gets the
same timestamp — the server start time. Compare the correct pattern in `TimeStatusMixin`
which uses a lambda.

**Fix:** `default=lambda: datetime.now(timezone.utc)`

---

### BUG 5 — Deprecated SQLAlchemy import
**File:** `app/database.py:3`

```python
from sqlalchemy.ext.declarative import declarative_base  # ← removed in SQLAlchemy 2.x
```

You have SQLAlchemy 2.0.45 in `requirements.txt`. This import is deprecated/removed.

**Fix:** `from sqlalchemy.orm import declarative_base`

---

### BUG 6 — Logger format error in `deploy_app`
**File:** `api/v1/apps.py:219`

```python
logger.error("Deployment failed for app %s", str(e))  # ← logs exception as app_id
```

The `%s` format arg should be `app_id`, not `str(e)`.

**Fix:** `logger.error("Deployment failed for app %s: %s", app_id, str(e))`

---

### BUG 7 — `docker_remove_container` silently swallows failures
**File:** `app/services/docker.py:78–95`

The function logs errors but never raises `DockerContainerRemovalError`.
If container removal fails during deploy, the flow continues silently and
tries to allocate a new port on a container that's still running.

---

### BUG 8 — `get_api_token` is a stub returning `None`
**File:** `app/utils.py:11`

```python
def get_api_token(request) -> str:
    pass   # ← returns None
```

Not connected to anything yet, but will break any auth dependency that calls it.

---

### BUG 9 — `clone_or_pull_repo` validates GitHub twice on deploy
**File:** `app/services/deploy.py:72`

`clone_or_pull_repo` internally calls `validate_github_repo()` which makes a
GitHub API call. On deploy this results in two GitHub API round-trips for no reason.
(Minor, but worth noting.)

---

## Part 2 — Completion Status

| Layer / Feature               | Status         | Notes                                      |
|-------------------------------|----------------|--------------------------------------------|
| FastAPI app setup             | Done           |                                            |
| Database (SQLite/SQLAlchemy)  | Done           | Deprecated import — fix it                 |
| App model (CRUD)              | Done           | `user_id` FK is a blocker                  |
| Create app endpoint           | Done*          | Blocked by `user_id` bug                   |
| List apps endpoint            | Done           |                                            |
| Get app detail endpoint       | Done*          | Blocked by `internal_port` not Optional    |
| Delete app endpoint           | Done           |                                            |
| Deploy endpoint               | Done           | Logger bug; container removal silent fail  |
| GitHub URL validation         | Done           |                                            |
| Git clone / pull              | Done           | Branch not checked out on clone            |
| Branch checkout               | Partial        | Done inside `docker_build`, not on clone   |
| Docker build                  | Done           |                                            |
| Docker run                    | Done           |                                            |
| Port manager                  | Done           |                                            |
| Error system                  | Done           | `ErrorLog.created_at` bug                  |
| Error logging to DB           | Done           |                                            |
| Users model                   | Done           | `role` default type bug                    |
| Password hashing utils        | Done           |                                            |
| Authentication (JWT/API key)  | Not started    | No endpoints, no middleware                |
| User registration/login       | Not started    |                                            |
| Nginx routing per app         | Not started    |                                            |
| Cloudflare tunnel             | Not started    |                                            |
| Tests                         | Not started    |                                            |

**Overall: ~45% complete (core engine done; auth, proxy, tests not started)**

---

## Part 3 — What To Do Next (Ordered by Priority)

---

### Step 1 — Fix the Bugs Above First (1–2 hours)

Fix all 9 bugs listed in Part 1 before writing any new code.
The `user_id` bug and `internal_port` bug alone will break your app end-to-end.

---

### Step 2 — Authentication System (highest priority new feature)

Without auth, your deployment API is publicly accessible — anyone can deploy
or delete apps. This is the next critical piece.

**What to build:**

#### 2a. User Registration endpoint
```
POST /api/auth/register
Body: { username, email, password }
Response: { id, username, email }
```
- Hash password with `hash_password()` from `app/utils.py` (already built)
- Save to `users` table (model already built)

#### 2b. User Login endpoint
```
POST /api/auth/login
Body: { username, password }
Response: { access_token, token_type: "bearer" }
```
- Verify password with `verify_password()` from `app/utils.py` (already built)
- Generate JWT token using `python-jose` (already in `requirements.txt`)
- Token payload: `{ sub: user_id, exp: <expiry> }`

#### 2c. Auth dependency (FastAPI `Depends`)
Create `app/auth.py`:
```python
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = ...) -> Users:
    # decode JWT, fetch user from DB, return user object
```

#### 2d. Protect write endpoints
Add `current_user: Users = Depends(get_current_user)` to:
- `POST /apps/create`
- `POST /apps/{id}/deploy`
- `DELETE /apps/delete/{id}`

#### 2e. Wire `user_id` into app creation
Once auth is in place, pass `current_user.id` as `user_id` when creating `AppModel`.

**New files to create:**
- `app/auth.py` — JWT encode/decode + `get_current_user` dependency
- `api/v1/auth.py` — register + login routes
- Update `api/__init__.py` to include auth router at `/api/auth`

---

### Step 3 — Nginx Routing Per Deployed App

This is your "service layer" routing piece. Each deployed app gets a subdomain
(`app-{id}.yourdomain.com`) routed to its internal port on the host.

**What to build:**

#### 3a. Nginx config template per app
When an app deploys successfully, generate a file like:
```
/etc/nginx/sites-available/app-{id}.conf
```
Contents:
```nginx
server {
    listen 80;
    server_name app-{id}.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:{internal_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### 3b. Nginx service in the app
Create `app/services/nginx.py` with:
- `write_nginx_config(app_model)` — writes config file
- `enable_nginx_config(app_id)` — symlinks to `sites-enabled/`
- `remove_nginx_config(app_id)` — removes config + symlink
- `reload_nginx()` — runs `subprocess.run(["nginx", "-s", "reload"])`

#### 3c. Hook into deploy and delete
- After `docker_run` succeeds in `deploy_app`: call `write_nginx_config` + `reload_nginx`
- In `delete_app`: call `remove_nginx_config` + `reload_nginx`

#### 3d. Store subdomain in DB (already done — `app.subdomain = f"app-{app_id}"`)
You already set `subdomain` at create time. Use it to build the `server_name`.

---

### Step 4 — Cloudflare Tunnel Integration

This exposes your local Nginx to the public internet via a Cloudflare tunnel.

**What to build:**

#### 4a. Install `cloudflared` on your server
```bash
# one-time setup
cloudflared tunnel login
cloudflared tunnel create gitdeploy
```

#### 4b. Wildcard subdomain routing
Configure your Cloudflare tunnel to route `*.yourdomain.com → localhost:80`
so Nginx handles per-subdomain routing.

Tunnel config (`~/.cloudflared/config.yml`):
```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: "*.yourdomain.com"
    service: http://localhost:80
  - service: http_status:404
```

#### 4c. DNS wildcard record
In Cloudflare dashboard, add:
```
CNAME  *  →  <tunnel-id>.cfargotunnel.com
```

#### 4d. (Optional) Automate via API
Cloudflare has an API to add DNS records programmatically.
You could call it from the deploy endpoint to register `app-{id}.yourdomain.com`
automatically on each new deploy. For now, the wildcard covers everything.

---

### Step 5 — Tests

After auth + nginx are in place, add tests.

**Priority order:**

#### 5a. Unit tests (no external deps)
- `test_validate_github_repo` — mock `requests.get`, test all error paths
- `test_allocate_free_port` — mock `socket.bind` + DB query
- `test_docker_command_builder` — test compile output, no mocking needed

#### 5b. API integration tests
- `POST /api/auth/register` → creates user
- `POST /api/auth/login` → returns token
- `POST /api/apps/create` (with token) → creates app
- `GET /api/apps/list/` → returns list
- `GET /api/apps/{id}` → returns detail (internal_port=None until deploy)
- `DELETE /api/apps/delete/{id}` → 204

#### 5c. Tools
- Use `pytest` (already in `requirements.txt`)
- Use `TestClient` from `starlette.testclient`
- Use SQLite in-memory DB for test isolation

---

## Part 4 — Suggested Build Order Summary

```
[ ] Step 1  Fix 9 bugs in Part 1                         (1–2 hrs)
[ ] Step 2a User registration endpoint                   (1 hr)
[ ] Step 2b User login + JWT generation                  (1 hr)
[ ] Step 2c Auth dependency (get_current_user)           (1 hr)
[ ] Step 2d Protect write endpoints + wire user_id       (30 min)
[ ] Step 3a Nginx config template function               (1 hr)
[ ] Step 3b nginx.py service (write/remove/reload)       (1 hr)
[ ] Step 3c Hook nginx into deploy + delete              (30 min)
[ ] Step 4  Cloudflare tunnel setup (one-time CLI setup) (1–2 hrs)
[ ] Step 5  Tests                                        (3–4 hrs)
```

---

## Part 5 — Files To Create / Modify

| Action   | File                         | Purpose                            |
|----------|------------------------------|------------------------------------|
| Modify   | `app/models/app_model.py`    | Fix `user_id` nullable temporarily |
| Modify   | `app/models/users.py`        | Fix `role` default                 |
| Modify   | `app/models/error_log.py`    | Fix `created_at` lambda            |
| Modify   | `app/schemas/app_detail_schema.py` | Make `internal_port` Optional |
| Modify   | `app/database.py`            | Fix deprecated import              |
| Modify   | `api/v1/apps.py`             | Fix logger bug, fix container removal |
| Create   | `app/auth.py`                | JWT encode/decode + dependency     |
| Create   | `api/v1/auth.py`             | Register + login routes            |
| Modify   | `api/__init__.py`            | Include auth router                |
| Create   | `app/services/nginx.py`      | Nginx config management            |
| Modify   | `api/v1/apps.py`             | Hook nginx into deploy + delete    |
| Create   | `tests/`                     | All test files                     |
