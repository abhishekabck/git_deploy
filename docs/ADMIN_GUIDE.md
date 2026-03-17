# Admin Guide — gitDeploy

This guide covers everything an administrator needs to operate, monitor, and maintain a gitDeploy installation.

---

## 1. Creating the First Admin User

The first admin account must be created via direct database access. gitDeploy does not expose a registration endpoint for admin accounts — there is no bootstrap admin in the default setup to prevent privilege escalation through the API.

### Option A — SQLite (default install)

```bash
sqlite3 /path/to/gitdeploy.db \
  "UPDATE users SET role='admin' WHERE username='your_username';"
```

Verify:
```bash
sqlite3 /path/to/gitdeploy.db \
  "SELECT id, username, email, role FROM users WHERE username='your_username';"
```

### Option B — PostgreSQL

```bash
psql -U your_db_user -d gitdeploy -c \
  "UPDATE users SET role='admin' WHERE username='your_username';"
```

### Option C — Promote via admin API (requires an existing admin)

```bash
curl -X PATCH http://localhost:8000/api/v1/admin/users/{user_id} \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

### Verify admin access

After promoting, login as the user and call the health endpoint:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/api/v1/admin/health \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

A successful response includes system metrics and app/user counts.

---

## 2. Admin Dashboard Walkthrough

The React frontend exposes an `/admin` route visible only to users with `role=admin`. The admin panel is divided into four sections.

### 2.1 System Health Panel

URL: `GET /api/v1/admin/health`

The health response contains:
```json
{
  "cpu": {"percent": 12.5, "count": 4},
  "memory": {"total_mb": 7962.0, "available_mb": 5200.1, "used_mb": 2761.9, "percent": 34.7},
  "disk": {"total_gb": 119.24, "free_gb": 87.41, "used_gb": 31.83, "percent": 26.7},
  "network": {"bytes_sent_mb": 145.22, "bytes_recv_mb": 892.11},
  "uptime_seconds": 86412,
  "apps": {"total": 12, "running": 10, "error": 1},
  "users": {"total": 5}
}
```

The frontend refreshes this data on a 15-second polling interval. Key indicators to watch:
- **CPU percent > 85%** sustained — a container may be in a tight loop; identify via `docker stats`
- **Memory percent > 80%** — consider upgrading RAM or applying stricter per-container `--memory` limits
- **Disk percent > 90%** — purge unused Docker images with `docker image prune -a` and remove unused app directories
- **error count > 0** — inspect the error log (Section 2.4)

### 2.2 App Management

URL: `GET /api/v1/admin/apps?page=1&size=50&filter_status=error`

Displays all apps across all users. Each row shows:
- App ID and name
- Owner user ID
- Repository URL and branch
- Status (created / prepared / running / error)
- Internal port and container port
- Created timestamp

**Common admin operations:**

Manually reset a stuck app to a recoverable state:
```bash
curl -X PATCH http://localhost:8000/api/v1/admin/apps/5 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "created"}'
```

Force-delete an abandoned app (user is gone, container is orphaned):
```bash
curl -X DELETE http://localhost:8000/api/v1/admin/apps/5 \
  -H "Authorization: Bearer $TOKEN"
```

This runs the full cleanup: `docker rm -f`, `docker rmi -f`, `shutil.rmtree` on the app and log directories, and removes the Nginx config file.

### 2.3 User Management

URL: `GET /api/v1/admin/users?page=1&size=50`

Displays all registered users. Each row shows:
- User ID, username, email
- Role (user / admin)
- Billing type (free / paid)
- Account creation timestamp

**Promote a user to admin:**
```bash
curl -X PATCH http://localhost:8000/api/v1/admin/users/3 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

**Upgrade billing tier:**
```bash
curl -X PATCH http://localhost:8000/api/v1/admin/users/3 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"billing_type": "paid"}'
```

**Delete a user account:**
```bash
curl -X DELETE http://localhost:8000/api/v1/admin/users/3 \
  -H "Authorization: Bearer $TOKEN"
```

This cascade-deletes all the user's apps: stops containers, removes images, deletes code and log directories, removes Nginx configs, and deletes all DB records.

### 2.4 Error Log Viewer

URL: `GET /api/v1/admin/errors?page=1&size=50`

Returns error events in reverse-chronological order. Each entry:
```json
{
  "id": 42,
  "error_code": "2002",
  "status_code": 500,
  "app_id": 7,
  "context": "Docker build failed with exit code 1",
  "created_at": "2026-03-17T14:22:31.000000"
}
```

**Error code reference:**

| Range   | Domain                | Common causes                                               |
|---------|-----------------------|-------------------------------------------------------------|
| 1000-1099 | Git / GitHub        | Invalid URL, private repo, clone failure, bad branch name   |
| 2000-2099 | Docker              | Dockerfile not found, build errors, port exhaustion         |
| 3000-3099 | App / Route         | App not found, deploy permission issues                     |
| 4000-4099 | Database            | Connection failures                                         |
| 5000-5099 | Internal            | Unexpected server errors                                    |

Full error code table is in `docs/ERROR_SYSTEM.md`.

**Investigating a deployment failure:**

1. Note the `app_id` from the error log entry.
2. Call `GET /api/v1/admin/apps` and find the app's `user_id`.
3. Check the context string — for Docker build errors it contains the exit code.
4. Connect to the server and inspect logs:
   ```bash
   # Application logs
   journalctl -u gitdeploy --since "1 hour ago" | grep "app_7"

   # Build output (streamed to the main logger during build)
   journalctl -u gitdeploy --since "1 hour ago" | grep "app_7_image"

   # Docker container logs (if the container ran before erroring)
   docker logs app_7_container
   ```

---

## 3. System Health Monitoring

### Log monitoring

The application logs to stdout/stderr with structured format:
```
2026-03-17 12:34:56,789 | INFO  | api.v1.apps     | Deploy triggered for app_id=7 user_id=3
2026-03-17 12:34:57,123 | INFO  | app.services.docker | Starting docker build for app_7_image
2026-03-17 12:35:12,456 | INFO  | app.services.docker | Docker build completed for app_7_image
```

When running as a systemd service, view logs with:
```bash
journalctl -u gitdeploy -f
```

### Docker resource monitoring

Check all running gitDeploy containers:
```bash
docker ps --filter "label=app_id"
```

Check resource usage per container:
```bash
docker stats $(docker ps -q --filter "label=app_id")
```

### Disk usage

Check disk usage of app directories:
```bash
du -sh /opt/apps/app-* | sort -h | tail -20
```

Check unused Docker images:
```bash
docker images --filter "dangling=true"
docker image prune -a --filter "label=app_id"
```

Note: `docker image prune -a --filter "label=app_id"` removes all gitDeploy images. Only run this if you intend to redeploy all apps.

---

## 4. Managing Apps

### Viewing all apps

```bash
curl -s "http://localhost:8000/api/v1/admin/apps?page=1&size=100" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Filter by status:
```bash
curl -s "http://localhost:8000/api/v1/admin/apps?filter_status=error" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Altering app status

The admin PATCH endpoint accepts `status` values: `created`, `prepared`, `running`, `error`.

Use cases:
- **Reset to `created`** — clears an error state so the user can redeploy
- **Set to `error`** — mark a broken app that needs user attention
- **Set to `running`** — manually mark an app as running after direct Docker intervention (use with caution)

```bash
curl -X PATCH http://localhost:8000/api/v1/admin/apps/7 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "created"}'
```

### Force-deleting an app

The admin delete is identical to the user delete except it bypasses ownership checks. It performs:
1. `docker ps -a -q -f name=app_{id}_container` → if found, `docker rm -f {container_id}`
2. `docker images -q app_{id}_image` → if found, `docker rmi -f {image_ids}`
3. `shutil.rmtree(BASE_APPS_DIR/app-{id})` → removes cloned code
4. `shutil.rmtree(BASE_LOGS_DIR/app-{id})` → removes log files
5. `remove_app_conf(id)` → removes `/etc/nginx/gitdeploy.d/app-{id}.conf`
6. `db.delete(app)` → removes DB record

```bash
curl -X DELETE http://localhost:8000/api/v1/admin/apps/7 \
  -H "Authorization: Bearer $TOKEN"
# Returns HTTP 204 No Content on success
```

---

## 5. Managing Users

### Listing users

```bash
curl -s "http://localhost:8000/api/v1/admin/users?page=1&size=100" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Promoting a user to admin

```bash
curl -X PATCH http://localhost:8000/api/v1/admin/users/{user_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

### Demoting an admin back to user

```bash
curl -X PATCH http://localhost:8000/api/v1/admin/users/{user_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "user"}'
```

### Deleting a user

Deleting a user cascades to all their apps. For each of the user's apps, the system performs the same cleanup as the admin app delete (Section 4). Only then is the user record deleted.

```bash
curl -X DELETE http://localhost:8000/api/v1/admin/users/{user_id} \
  -H "Authorization: Bearer $TOKEN"
# Returns HTTP 204 No Content on success
```

**Note:** If the user being deleted is the only admin, you will lose admin access. Promote another user first.

---

## 6. Error Log Analysis

### Querying error logs

```bash
# Latest 50 errors
curl -s "http://localhost:8000/api/v1/admin/errors?page=1&size=50" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Common error patterns and resolutions

**Error 1004 — Repo not found or private**
- User submitted a private GitHub repository URL.
- Resolution: inform the user that only public repositories are supported. If the repo should be public, ask them to check their GitHub visibility settings.

**Error 1007 — Git clone failed**
- Network issue or GitHub was temporarily unavailable.
- Check outbound connectivity: `curl https://api.github.com`
- The user can retry the deployment once connectivity is restored.

**Error 2000 — Dockerfile not found**
- The `dockerfile_path` the user specified does not exist in the repository.
- Resolution: admin sets the app's branch back to `created` via PATCH so the user can redeploy with a corrected `dockerfile_path`.

**Error 2002 — Docker build failed**
- Application code has a build error (missing dependencies, syntax error in Dockerfile, etc.)
- Check the context string; it contains the Docker exit code.
- Advise the user to test the Dockerfile locally before deploying.

**Error 2005 — Docker run failed**
- Container started but immediately exited with an error.
- Check the context for the stderr output.
- Run `docker logs app_{id}_container` for the last known log output.

**Error 2006 — No available port**
- All ports in 10000–65535 are occupied (or stuck in TIME_WAIT).
- Run `ss -tlnp | grep -c '1[0-9]\{4\}'` to count active ports.
- Ports in TIME_WAIT will release automatically; wait 60 seconds and retry.
- Consider cleaning up unused apps.

---

## 7. Key Rotation for the Secret Manager

When the sidecar encryption key must be rotated (security policy, suspected compromise):

### Step 1 — Generate a new Fernet key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Example output: b'abc123...='  (URL-safe base64, 44 chars)
```

### Step 2 — Initiate rotation via API

```bash
curl -X POST http://localhost:8001/admin/rotate-key \
  -H "X-Api-Key: $SIDECAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"new_key\": \"<new_fernet_key>\"}"
```

Expected response:
```json
{"rotated": 5}
```

The number `rotated` is the count of successfully re-encrypted records. If it is less than the total number of apps with secrets, some records failed — check the sidecar logs for details.

### Step 3 — Update the environment variable

Update `SIDECAR_ENCRYPTION_KEY` in your environment or `.env` file:
```env
SIDECAR_ENCRYPTION_KEY=<new_fernet_key>
```

Restart the sidecar process so the next startup reads the new key from the environment (in-memory key was already updated by the rotation endpoint, but after restart the env var is the source of truth).

### Step 4 — Verify

```bash
# Should return decrypted secrets if rotation succeeded
curl http://localhost:8001/secrets/1 \
  -H "X-Api-Key: $SIDECAR_API_KEY"
```

---

## 8. Routine Maintenance Tasks

### Weekly

- Review the error log for recurring patterns.
- Check disk usage: `df -h` and `du -sh /opt/apps/*`.
- Prune dangling Docker images: `docker image prune`.

### Monthly

- Rotate the sidecar encryption key (if policy requires it).
- Review user accounts — delete inactive accounts.
- Verify Alembic migration state: `alembic current`.

### Before upgrades

1. Back up the database: `cp gitdeploy.db gitdeploy.db.bak` (SQLite) or `pg_dump gitdeploy > backup.sql` (PostgreSQL).
2. Back up the sidecar database: `cp secrets.db secrets.db.bak`.
3. Note the current `SIDECAR_ENCRYPTION_KEY` — losing this key means losing all stored secrets.
4. Apply migrations after upgrading: `alembic upgrade head`.
