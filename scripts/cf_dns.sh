#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# cf_dns.sh — Manage Cloudflare DNS records for gitDeploy
#
# Usage:
#   ./scripts/cf_dns.sh setup          # Create @, *, api CNAMEs for tunnel
#   ./scripts/cf_dns.sh list           # List all DNS records
#   ./scripts/cf_dns.sh add <name> <type> <content> [proxied]
#   ./scripts/cf_dns.sh delete <name>  # Delete record by name
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

# ── Load .env ────────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env not found at $ENV_FILE" >&2
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

# ── Validate required vars ──────────────────────────────────────────────────
for var in CF_ZONE_ID CF_API_TOKEN CF_TUNNEL_ID APP_DOMAIN; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: $var is not set in .env" >&2
        exit 1
    fi
done

API="https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records"
TUNNEL_TARGET="$CF_TUNNEL_ID.cfargotunnel.com"

# ── Helpers ──────────────────────────────────────────────────────────────────
cf_api() {
    local method="$1" url="$2"
    shift 2
    curl -s -X "$method" "$url" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        "$@"
}

check_success() {
    local resp="$1" label="$2"
    local ok
    ok=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "False")
    if [[ "$ok" == "True" ]]; then
        echo "  ✓ $label"
    else
        local errors
        errors=$(echo "$resp" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for e in d.get('errors', []):
    print(f\"  code {e.get('code')}: {e.get('message')}\")
" 2>/dev/null || echo "  unknown error")
        echo "  ✗ $label"
        echo "$errors"
    fi
}

add_record() {
    local name="$1" type="$2" content="$3" proxied="${4:-true}"
    local resp
    resp=$(cf_api POST "$API" \
        --json "{\"type\":\"$type\",\"name\":\"$name\",\"content\":\"$content\",\"ttl\":1,\"proxied\":$proxied}")
    check_success "$resp" "$type $name → $content (proxied=$proxied)"
}

# ── Commands ─────────────────────────────────────────────────────────────────
cmd_setup() {
    echo "Setting up DNS for $APP_DOMAIN → tunnel $CF_TUNNEL_ID"
    echo "Target: $TUNNEL_TARGET"
    echo ""
    add_record "@"   CNAME "$TUNNEL_TARGET" true
    add_record "*"   CNAME "$TUNNEL_TARGET" true
    add_record "api" CNAME "$TUNNEL_TARGET" true
    echo ""
    echo "Done. Records may take a minute to propagate."
}

cmd_list() {
    local resp
    resp=$(cf_api GET "$API?per_page=50")
    echo "$resp" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if not data.get('success'):
    print('ERROR:', data.get('errors'))
    sys.exit(1)
records = data.get('result', [])
if not records:
    print('No DNS records found.')
    sys.exit(0)
print(f\"{'Type':<8} {'Name':<40} {'Content':<50} {'Proxied'}\")
print('-' * 110)
for r in sorted(records, key=lambda x: x['name']):
    print(f\"{r['type']:<8} {r['name']:<40} {r['content']:<50} {r['proxied']}\")
"
}

cmd_add() {
    local name="${1:?Usage: cf_dns.sh add <name> <type> <content> [proxied]}"
    local type="${2:?Missing record type (A, CNAME, TXT, etc.)}"
    local content="${3:?Missing record content}"
    local proxied="${4:-true}"
    add_record "$name" "$type" "$content" "$proxied"
}

cmd_delete() {
    local name="${1:?Usage: cf_dns.sh delete <name>}"
    # Resolve full name
    local full_name
    if [[ "$name" == "@" ]]; then
        full_name="$APP_DOMAIN"
    elif [[ "$name" == *"$APP_DOMAIN"* ]]; then
        full_name="$name"
    else
        full_name="$name.$APP_DOMAIN"
    fi

    # Find record ID
    local resp
    resp=$(cf_api GET "$API?name=$full_name")
    local record_id
    record_id=$(echo "$resp" | python3 -c "
import sys, json
data = json.load(sys.stdin)
results = data.get('result', [])
if results:
    print(results[0]['id'])
" 2>/dev/null)

    if [[ -z "$record_id" ]]; then
        echo "  ✗ No record found for $full_name"
        return 1
    fi

    resp=$(cf_api DELETE "$API/$record_id")
    check_success "$resp" "Deleted $full_name"
}

# ── Main ─────────────────────────────────────────────────────────────────────
case "${1:-}" in
    setup)  cmd_setup ;;
    list)   cmd_list ;;
    add)    shift; cmd_add "$@" ;;
    delete) shift; cmd_delete "$@" ;;
    *)
        echo "Usage: cf_dns.sh {setup|list|add|delete}"
        echo ""
        echo "  setup              Create @, *, api CNAMEs pointing to tunnel"
        echo "  list               List all DNS records"
        echo "  add <n> <t> <c>    Add record (name, type, content)"
        echo "  delete <name>      Delete record by name"
        exit 1
        ;;
esac
