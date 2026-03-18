# gitDeploy — Runbook

Complete guide to set up and run the full stack: backend API, frontend UI, Nginx, and optional Cloudflare Tunnel.

---

## Prerequisites

Make sure these are installed before starting:

| Tool | Min Version | Check |
|------|-------------|-------|
| Python | 3.12+ | `python3 --version` |
| pip | any | `pip --version` |
| Git | any | `git --version` |
| Docker | any | `docker --version` |
| Node.js | 22.12+ | `node --version` |
| npm | 10+ | `npm --version` |
| Nginx | any | `nginx -v` |

> **Node.js upgrade** (if you have Node 18):
> ```bash
> curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
> sudo apt-get install -y nodejs
> ```

---

## Part 1 — Backend

### 1.1 Install dependencies

```bash
cd /root/Projects/gitDeploy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1.2 Configure environment

Edit the `.env` file (already exists at `/root/Projects/gitDeploy/.env`):

```bash
nano .env
```

Set these values — the rest have safe defaults:

```env
# Required — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=your-long-random-secret-here

# Your real domain (used for nginx app URLs: app-{id}.yourdomain.com)
APP_DOMAIN=yourdomain.com

# Allow requests from your frontend
CORS_ORIGINS=http://localhost:5173,https://yourdomain.com

# Set to the correct DB file (default is gitdeploy.db)
DB_URL=sqlite+aiosqlite:///./gitdeploy.db

# Enable Nginx automation
NGINX_ENABLED=true
NGINX_AUTO_RELOAD=true
NGINX_CONF_DIR=/etc/nginx/gitdeploy.d

# Directories for cloned repos and logs
BASE_APPS_DIR=/opt/apps
BASE_LOGS_DIR=/opt/logs
```

Create the required directories:

```bash
sudo mkdir -p /opt/apps /opt/logs
```

### 1.3 Set up the database

```bash
cd /root/Projects/gitDeploy
source .venv/bin/activate
alembic upgrade head
```

> Tables are also auto-created on first startup, but running Alembic is best practice.

### 1.4 Start the backend

```bash
cd /root/Projects/gitDeploy
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it is running:

```bash
curl http://localhost:8000/
# Expected: {"status": "ok", ...}
```

API docs available at: `http://localhost:8000/docs`

---

## Part 2 — Nginx Setup (automatic per-app routing)

Run this **once**. It creates the include directory and wires it into Nginx.

### 2.1 Run the setup script

```bash
cd /root/Projects/gitDeploy
sudo bash scripts/setup_nginx.sh --domain yourdomain.com --apply
```

This does:
- Creates `/etc/nginx/gitdeploy.d/` directory
- Writes `/etc/nginx/sites-available/gitdeploy.conf` with `include /etc/nginx/gitdeploy.d/*.conf;`
- Symlinks it into `sites-enabled/`
- Reloads Nginx

### 2.2 Verify

```bash
sudo nginx -t
# Expected: syntax is ok / test is successful

ls /etc/nginx/gitdeploy.d/
# Empty now — app configs appear here automatically after each deploy
```

After this, every time an app is deployed via the API, gitDeploy will automatically:
- Write `/etc/nginx/gitdeploy.d/app-{id}.conf`
- Run `nginx -s reload`

On app deletion, the config file is removed and Nginx is reloaded automatically.

---

## Part 3 — Frontend UI

### 3.1 Install dependencies

```bash
cd /root/Projects/gitdeploy-ui

# If node_modules exists from a different OS (e.g. Windows), clean first:
rm -rf node_modules package-lock.json

npm install
```

### 3.2 Configure environment

```bash
nano .env
```

```env
# Point this to your backend IP:port
API_PROXY_TARGET=http://localhost:8000

# Leave empty in dev — Vite proxy handles /api/* calls
VITE_API_URL=

# Domain shown in app URLs
VITE_APP_DOMAIN=yourdomain.com
```

### 3.3 Start the frontend

```bash
cd /root/Projects/gitdeploy-ui
npm run dev
```

Open: `http://localhost:5173`

From other devices on the same network:
```bash
hostname -I   # find your machine's LAN IP
# then open http://<your-ip>:5173 on any device
```

---

## Part 4 — First Login & Admin Setup

### 4.1 Register your account

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"yourpassword"}'
```

### 4.2 Promote to admin

The first user needs to be manually promoted via SQLite:

```bash
sqlite3 /root/Projects/gitDeploy/gitdeploy.db \
  "UPDATE users SET role = 'admin' WHERE email = 'admin@example.com';"
```

### 4.3 Login

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"yourpassword"}'
# Returns: { "access_token": "..." }
```

---

## Part 5 — Deploy Your First App

```bash
# 1. Save your token
TOKEN="paste-your-access-token-here"

# 2. Create the app record
curl -X POST http://localhost:8000/api/v1/apps/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-app",
    "repo_url": "https://github.com/owner/repo",
    "branch": "main",
    "container_port": 3000
  }'
# Returns: { "id": 1, ... }

# 3. Deploy it (clone + docker build + docker run)
curl -X POST http://localhost:8000/api/v1/apps/1/deploy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

After deploy:
- App runs on a dynamic internal port (10000–65535)
- Nginx config auto-written: `/etc/nginx/gitdeploy.d/app-1.conf`
- Accessible at: `http://app-1.yourdomain.com`

---

## Part 6 — Cloudflare Tunnel (optional, for public internet access)

Use this to expose your server publicly without opening inbound firewall ports.

### 6.1 Prerequisites

```bash
# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Login to Cloudflare
cloudflared tunnel login

# Create the tunnel
cloudflared tunnel create gitdeploy
# Note the Tunnel ID printed (UUID format)
```

### 6.2 Generate config

```bash
cd /root/Projects/gitDeploy
bash scripts/setup_cloudflare_tunnel.sh \
  --tunnel-id <YOUR-TUNNEL-UUID> \
  --domain yourdomain.com
```

### 6.3 Add DNS records

In your Cloudflare Dashboard (or via CLI):

```bash
cloudflared tunnel route dns gitdeploy api.yourdomain.com
cloudflared tunnel route dns gitdeploy yourdomain.com
cloudflared tunnel route dns gitdeploy '*.yourdomain.com'
```

### 6.4 Start the tunnel

```bash
cloudflared tunnel run gitdeploy
```

To run as a system service (survives reboots):

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

Traffic flow with Cloudflare Tunnel:

```
Internet → Cloudflare → cloudflared (on your server) → Nginx :80 → app container
```

---

## Daily Start (after first-time setup)

Open three terminals:

**Terminal 1 — Backend:**
```bash
cd /root/Projects/gitDeploy
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```bash
cd /root/Projects/gitdeploy-ui
npm run dev
```

**Terminal 3 — (optional) Cloudflare Tunnel:**
```bash
cloudflared tunnel run gitdeploy
```

> If cloudflared is installed as a system service, Terminal 3 is not needed.

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_URL` | `sqlite+aiosqlite:///./gitdeploy.db` | Database connection URL |
| `JWT_SECRET` | random (insecure) | **Always set this in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh cookie TTL |
| `APP_DOMAIN` | `localhost` | Base domain for app URLs |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins |
| `BASE_APPS_DIR` | `/opt/apps` | Where cloned repos are stored |
| `BASE_LOGS_DIR` | `/opt/logs` | Where Docker logs are stored |
| `NGINX_ENABLED` | `false` | Auto-write nginx configs on deploy |
| `NGINX_AUTO_RELOAD` | `false` | Run `nginx -s reload` after each change |
| `NGINX_CONF_DIR` | `/etc/nginx/gitdeploy.d` | Directory for per-app nginx configs |
| `REDIS_ENABLED` | `false` | Enable Redis caching layer |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `SIDECAR_URL` | `http://localhost:8001` | Secret Manager Sidecar URL |
| `SIDECAR_API_KEY` | random (insecure) | Shared key with sidecar — always set |

---

## Troubleshooting

### Backend won't start
```bash
# Check for port conflict
lsof -i :8000

# Check Python version
python3 --version   # must be 3.12+

# Check .env is loaded
grep DB_URL .env
```

### Frontend can't reach backend (CORS / 502)
```bash
# Confirm backend is up
curl http://localhost:8000/

# Check API_PROXY_TARGET in gitdeploy-ui/.env
cat /root/Projects/gitdeploy-ui/.env

# Restart Vite after changing .env
# Ctrl+C → npm run dev
```

### Deployed app not accessible via subdomain
```bash
# Check nginx config was written
ls /etc/nginx/gitdeploy.d/

# Test nginx config
sudo nginx -t

# Manually reload nginx
sudo nginx -s reload

# Check app is actually running
docker ps | grep app_
```

### Frontend shows stale user data after DB edit
Log out and log back in — the user object is cached in the browser session. A fresh login triggers `/api/v1/auth/me` and fetches updated data.

### Database edited wrong file
The backend reads from `gitdeploy.db` (set via `DB_URL` in `.env`). Always edit the correct file:
```bash
sqlite3 /root/Projects/gitDeploy/gitdeploy.db ".tables"
```

### Port conflict on deploy
```bash
# Check what is using the port
lsof -i :<port>

# Check all allocated ports in DB
sqlite3 gitdeploy.db "SELECT name, internal_port FROM apps;"
```

---

## Ports Summary

| Service | Port | Notes |
|---------|------|-------|
| Backend API | 8000 | FastAPI / Uvicorn |
| Frontend (dev) | 5173 | Vite dev server |
| Secret Sidecar | 8001 | Optional |
| Deployed apps | 10000–65535 | Auto-allocated per app |
| Nginx HTTP | 80 | Reverse proxy for all apps |
| Nginx HTTPS | 443 | Configure manually with SSL certs |
