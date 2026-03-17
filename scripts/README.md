# gitDeploy — Infrastructure Scripts

These scripts automate Nginx and Cloudflare Tunnel configuration for gitDeploy.
They only write configuration files — they do NOT restart services or activate tunnels
unless you explicitly pass the `--apply` flag.

## Scripts

| Script | Purpose |
|--------|---------|
| `setup_nginx.sh` | Install and configure Nginx for subdomain routing |
| `add_app_to_nginx.sh` | Add a single app's subdomain block to Nginx |
| `remove_app_from_nginx.sh` | Remove an app's Nginx block |
| `setup_cloudflare_tunnel.sh` | Configure a Cloudflare Tunnel for gitDeploy |
| `add_app_to_tunnel.sh` | Add a subdomain route to an existing Cloudflare Tunnel |
| `generate_nginx_conf.py` | Python helper to generate Nginx config blocks |

## Quick Start

### Nginx

```bash
# 1. Set up master Nginx config (does NOT restart nginx without --apply)
./scripts/setup_nginx.sh --domain yourdomain.com

# 2. Add an app
./scripts/add_app_to_nginx.sh --app-id 1 --port 10000 --domain yourdomain.com

# 3. Apply (reload nginx)
sudo nginx -s reload
```

### Cloudflare Tunnel

```bash
# 1. Create a tunnel first (cloudflared CLI):
#    cloudflared tunnel create gitdeploy
#    Note the tunnel ID from the output.

# 2. Configure the tunnel config file
./scripts/setup_cloudflare_tunnel.sh \
  --tunnel-id YOUR_TUNNEL_ID \
  --domain yourdomain.com

# 3. Add an app route
./scripts/add_app_to_tunnel.sh \
  --tunnel-id YOUR_TUNNEL_ID \
  --app-id 1 \
  --domain yourdomain.com

# 4. Start the tunnel (manual step)
cloudflared tunnel run gitdeploy
```
