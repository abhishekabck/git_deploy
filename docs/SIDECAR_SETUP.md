# Secret Manager Sidecar — Setup Guide

The secret manager sidecar is a companion FastAPI service that runs alongside the
main gitDeploy API. It stores per-app environment variable secrets using AES
encryption (Fernet / AES-128-CBC + HMAC-SHA256).

## Architecture

```
┌─────────────────┐    X-Api-Key    ┌──────────────────────────┐
│  gitDeploy API  │ ─────────────── │  Secret Manager Sidecar  │
│  (port 8000)    │    HTTP/REST    │  (port 8001)             │
└─────────────────┘                 └──────────────────────────┘
                                              │
                                    ┌─────────────────┐
                                    │  secrets.db     │
                                    │  (SQLite,       │
                                    │   encrypted)    │
                                    └─────────────────┘
```

## Setup

### 1. Generate an encryption key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output. This is your `SIDECAR_ENCRYPTION_KEY`. **Store it securely — losing it means losing all secrets.**

### 2. Create the sidecar `.env` file

```bash
cp /root/Projects/gitDeploy/sidecar/.env.example /root/Projects/gitDeploy/sidecar/.env
```

Edit `/root/Projects/gitDeploy/sidecar/.env`:
```
SIDECAR_API_KEY=your-shared-api-key-here
SIDECAR_ENCRYPTION_KEY=your-fernet-key-here
SIDECAR_DB_PATH=/opt/secrets/secrets.db
```

### 3. Set matching key in main app `.env`

```
SIDECAR_URL=http://localhost:8001
SIDECAR_API_KEY=your-shared-api-key-here
```

### 4. Install dependencies

```bash
cd /root/Projects/gitDeploy/sidecar
pip install -r requirements.txt
```

### 5. Run the sidecar

```bash
cd /root/Projects/gitDeploy
python -m sidecar.main
```

Or with uvicorn directly:
```bash
uvicorn sidecar.main:app --host 0.0.0.0 --port 8001
```

### 6. Run with systemd (production)

Create `/etc/systemd/system/gitdeploy-sidecar.service`:
```ini
[Unit]
Description=gitDeploy Secret Manager Sidecar
After=network.target

[Service]
User=root
WorkingDirectory=/root/Projects/gitDeploy
EnvironmentFile=/root/Projects/gitDeploy/sidecar/.env
ExecStart=/usr/local/bin/uvicorn sidecar.main:app --host 0.0.0.0 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable gitdeploy-sidecar
systemctl start gitdeploy-sidecar
```

## API Reference

All endpoints require `X-Api-Key` header matching `SIDECAR_API_KEY`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| POST | `/secrets/{app_id}` | Store/update secrets |
| GET | `/secrets/{app_id}` | Retrieve decrypted secrets |
| DELETE | `/secrets/{app_id}` | Delete secrets |
| GET | `/secrets` | List all app IDs with secrets |
| POST | `/admin/rotate-key` | Re-encrypt all secrets with new key |

## Key Rotation

To rotate the encryption key without downtime:

```bash
NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
curl -X POST http://localhost:8001/admin/rotate-key \
  -H "X-Api-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d "{\"new_key\": \"$NEW_KEY\"}"
```

After success, update `SIDECAR_ENCRYPTION_KEY` in your `.env` file and restart the sidecar.
