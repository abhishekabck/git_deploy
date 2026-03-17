# Cloudflare Tunnel Setup for gitDeploy

This guide explains how to expose gitDeploy apps to the internet using
Cloudflare Tunnels — without opening any inbound firewall ports.

## Prerequisites

- A domain managed in Cloudflare
- `cloudflared` CLI installed ([download](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/))
- Nginx installed and running on the host server

## Architecture

```
Internet
   │
   ▼
Cloudflare Edge (DNS: *.yourdomain.com → tunnel)
   │  (encrypted tunnel, no open ports needed)
   ▼
cloudflared daemon (running on your server)
   │
   ▼
Nginx (:80) — routes subdomains to internal ports
   │
   ├── app-1.yourdomain.com  →  127.0.0.1:10000
   ├── app-2.yourdomain.com  →  127.0.0.1:10001
   └── app-N.yourdomain.com  →  127.0.0.1:10NNN
```

## Step-by-Step Setup

### Step 1: Authenticate cloudflared

```bash
cloudflared tunnel login
```

This opens a browser. Select your domain. A credentials file is saved to `~/.cloudflared/`.

### Step 2: Create the tunnel

```bash
cloudflared tunnel create gitdeploy
```

Note the **Tunnel ID** from the output (a UUID like `abc123...`).

### Step 3: Configure Nginx

```bash
# Run as root or with sudo
./scripts/setup_nginx.sh --domain yourdomain.com --apply
```

### Step 4: Configure the Cloudflare Tunnel

```bash
./scripts/setup_cloudflare_tunnel.sh \
  --tunnel-id YOUR_TUNNEL_UUID \
  --domain yourdomain.com
```

This writes `~/.cloudflared/config.yml`. Review it before proceeding.

### Step 5: Add DNS records

In the **Cloudflare Dashboard → DNS**:

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | `*` | `YOUR_TUNNEL_UUID.cfargotunnel.com` | Proxied |
| CNAME | `@` | `YOUR_TUNNEL_UUID.cfargotunnel.com` | Proxied |
| CNAME | `api` | `YOUR_TUNNEL_UUID.cfargotunnel.com` | Proxied |

Or via CLI:
```bash
cloudflared tunnel route dns gitdeploy "*.yourdomain.com"
cloudflared tunnel route dns gitdeploy "yourdomain.com"
cloudflared tunnel route dns gitdeploy "api.yourdomain.com"
```

### Step 6: Start the tunnel

```bash
cloudflared tunnel run gitdeploy
```

To run as a system service:
```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### Step 7: Deploy an app and add its Nginx block

When gitDeploy deploys an app (e.g. app-1 on port 10000):

```bash
./scripts/add_app_to_nginx.sh \
  --app-id 1 \
  --port 10000 \
  --domain yourdomain.com \
  --apply
```

The app is now accessible at `https://app-1.yourdomain.com`.

## Automating Nginx Updates

The gitDeploy API can call these scripts automatically after successful deployments.
Set in your main `.env`:

```
APP_DOMAIN=yourdomain.com
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Tunnel not connecting | Check `cloudflared tunnel run gitdeploy` output |
| App subdomain not resolving | Verify DNS CNAME in Cloudflare dashboard |
| 502 Bad Gateway | Check that the container is running: `docker ps` |
| Nginx not routing | Check `sudo nginx -t` and `/etc/nginx/gitdeploy.d/` |
