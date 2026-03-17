#!/usr/bin/env bash
# add_app_to_tunnel.sh — Add a new app subdomain to the Cloudflare Tunnel config.
# This ONLY updates the config file — it does NOT reload the tunnel.
# You must restart or send SIGHUP to cloudflared after updating the config.
#
# Usage: ./add_app_to_tunnel.sh --tunnel-id <id> --app-id <id> --domain <domain>
set -euo pipefail

TUNNEL_ID=""
APP_ID=""
DOMAIN=""
CONFIG_DIR="${HOME}/.cloudflared"

usage() {
  echo "Usage: $0 --tunnel-id <id> --app-id <id> --domain <domain> [--config-dir <dir>]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --tunnel-id)  TUNNEL_ID="$2"; shift 2 ;;
    --app-id)     APP_ID="$2"; shift 2 ;;
    --domain)     DOMAIN="$2"; shift 2 ;;
    --config-dir) CONFIG_DIR="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -z "$TUNNEL_ID" || -z "$APP_ID" || -z "$DOMAIN" ]] && usage

SUBDOMAIN="app-${APP_ID}.${DOMAIN}"
CONFIG_FILE="${CONFIG_DIR}/config.yml"

echo "==> NOTE: gitDeploy uses a wildcard Cloudflare Tunnel entry (*.${DOMAIN})"
echo "==> All app subdomains are automatically routed through Nginx."
echo "==> You only need to run this script if your tunnel config does NOT"
echo "==> already have a wildcard '*.${DOMAIN}' entry."
echo ""
echo "==> App subdomain: ${SUBDOMAIN}"
echo "==> Internal route: Nginx -> 127.0.0.1:<internal_port>"
echo ""
echo "==> To manually add a DNS record for this specific app:"
echo "    cloudflared tunnel route dns gitdeploy ${SUBDOMAIN}"
echo ""
echo "==> After any config change, reload the tunnel:"
echo "    sudo systemctl reload cloudflared"
echo "    # or: kill -HUP \$(pgrep cloudflared)"
