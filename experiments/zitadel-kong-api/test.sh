#!/usr/bin/env bash
# End-to-end smoke test for the Zitadel + Kong + API stack, driven by the `zk` CLI.
#
# Prerequisites:
#   - Zitadel running at $ZITADEL_ISSUER (default http://localhost:8080)
#   - This stack running:  docker compose up --build
#   - .env with ZITADEL_CLIENT_ID / ZITADEL_CLIENT_SECRET (app must allow
#     client_credentials and have Auth Token Type = JWT)
#
# Usage:  ./test.sh
set -euo pipefail
cd "$(dirname "$0")"

# Load .env (ZITADEL_ISSUER / ZITADEL_CLIENT_ID / ZITADEL_CLIENT_SECRET).
[ -f .env ] && set -a && . ./.env && set +a

ISSUER="${ZITADEL_ISSUER:-http://localhost:8080}"
KONG="${KONG_URL:-http://localhost:8000}"

# Build the zk CLI. go.mod lives in cli/, so build from inside that module and
# emit the binary back here as an absolute path. Pick the name per OS.
BINNAME=zk
case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) BINNAME=zk.exe ;; esac
BIN="$(pwd)/$BINNAME"
echo "==> building zk"
(cd cli && go build -o "$BIN" .)

# Bring up both stacks. They are separate compose projects joined by the shared
# external `edge` network — Kong fronts the API but neither owns the other.
echo "==> ensuring shared network + stacks are up"
docker network create edge >/dev/null 2>&1 || true
docker compose -f api/docker-compose.yml up -d --build   # API stack
docker compose up -d --build                             # gateway stack (this file)

echo "==> waiting for Kong to accept traffic"
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$KONG/api/hello" || true)
  [ "$code" != "000" ] && break
  sleep 1
done

echo "==> 1. no token → Kong should reject (expect 401)"
curl -s -o /dev/null -w "   status=%{http_code}\n" "$KONG/api/hello"

echo "==> 2. fetch a JWT access token from Zitadel via zk"
# zk picks the credential from the environment: ZITADEL_KEY_FILE (Private Key
# JWT) or ZITADEL_CLIENT_ID + ZITADEL_CLIENT_SECRET (client secret).
TOKEN=$("$BIN" token --issuer "$ISSUER")
echo "   token: ${TOKEN:0:24}…"

echo "==> 3. call the protected API through Kong (expect 200 + hello world)"
curl -s -w "\n   status=%{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" "$KONG/api/hello"

echo "==> 4. debug headers"
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/debug/headers | python -m json.tool