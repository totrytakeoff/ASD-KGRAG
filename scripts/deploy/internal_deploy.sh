#!/usr/bin/env bash
set -euo pipefail

ROOT="${DEPLOY_ROOT:-/opt/asd-kgrag}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
NGINX_TARGET="${NGINX_TARGET:-/etc/nginx/conf.d/asd-kgrag.conf}"
SERVER_NAME="${SERVER_NAME:-_}"

if [[ ! "$SERVER_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid SERVER_NAME: $SERVER_NAME" >&2
  exit 2
fi

cd "$ROOT/frontend"
pnpm build

cd "$ROOT"
docker compose -f "$COMPOSE_FILE" build qa-api
docker compose -f "$COMPOSE_FILE" up -d neo4j qdrant qa-api

nginx_rendered="$(mktemp)"
trap 'rm -f "$nginx_rendered"' EXIT
sed "s/server_name _;/server_name ${SERVER_NAME};/" deploy/nginx/asd-kgrag.conf > "$nginx_rendered"
install -m 0644 "$nginx_rendered" "$NGINX_TARGET"
nginx -t
systemctl reload nginx

wait_for_url() {
  local url="$1"
  local attempts="${2:-24}"
  local delay_seconds="${3:-5}"
  local attempt
  for attempt in $(seq 1 "$attempts"); do
    if curl -fsS "$url" 2>/dev/null; then
      printf '\n'
      return 0
    fi
    sleep "$delay_seconds"
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

wait_for_url http://127.0.0.1:8010/health
wait_for_url http://127.0.0.1:8010/health/deep 6 5
