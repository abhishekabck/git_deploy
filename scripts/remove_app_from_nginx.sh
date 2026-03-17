#!/usr/bin/env bash
# remove_app_from_nginx.sh — Remove a deployed app's Nginx block.
# Usage: ./remove_app_from_nginx.sh --app-id <id> [--apply]
set -euo pipefail

APP_ID=""
APPLY=false
GITDEPLOY_D="/etc/nginx/gitdeploy.d"

usage() {
  echo "Usage: $0 --app-id <id> [--apply]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --app-id) APP_ID="$2"; shift 2 ;;
    --apply)  APPLY=true; shift ;;
    *) usage ;;
  esac
done

[[ -z "$APP_ID" ]] && usage

CONF_FILE="${GITDEPLOY_D}/app-${APP_ID}.conf"

if [[ -f "$CONF_FILE" ]]; then
  echo "==> Removing ${CONF_FILE}"
  sudo rm -f "$CONF_FILE"
  echo "==> Config removed."
else
  echo "==> No config found for app-${APP_ID} (already removed?)."
fi

if $APPLY; then
  sudo nginx -t && sudo nginx -s reload
  echo "==> Nginx reloaded."
else
  echo "==> Run 'sudo nginx -s reload' to apply."
fi
