# Zitadel + Kong + API (local)

Kong Gateway (DB-less, **open-source only**) validating JWT access tokens issued
by your **existing** Zitadel instance, in front of a small FastAPI backend.

Zitadel itself is **not** part of this stack — it runs separately from (Traefik on host port `8080`, issuer
`http://localhost:8080`). This project is only the **Kong + API** side.

## How token validation works (no enterprise plugin)

Kong's enterprise OIDC plugin isn't used. Instead we use the bundled OSS **`jwt`**
plugin, which verifies an `RS256` signature against a PEM public key. A one-shot
`kong-init` container — the **`zk` Go CLI** (`zk gen-config`) — downloads
Zitadel's JWKS at startup, converts the active signing key to PEM, and writes the
declarative `kong.yml`. Kong then validates every `Authorization: Bearer <jwt>`
on `/api/*` locally — no runtime call to Zitadel, no database.

Both jobs (rendering the config and fetching tokens) are a single
**dependency-free Go binary** in `cli/` — no Python or shell toolchain to
install. It builds to a `scratch` image for the init container and also runs
natively on any OS via `go build ./cli`.

## Folder structure

The gateway and the API are **separate compose projects**, joined by a shared
external Docker network (`edge`). Kong fronts the API but neither owns the
other's lifecycle — this is the seam where you'd later move Kong into its own
repo/deployment.

```
zitadel-kong-api/
├── docker-compose.yml          # GATEWAY stack: kong-init (zk) -> kong   (project "kong-gateway")
├── .env.example                # copy to .env (defaults match local Zitadel)
├── cli/                         # the `zk` CLI (single static Go binary)
│   ├── Dockerfile              # builds to a scratch image
│   ├── go.mod
│   ├── main.go                 # subcommand dispatch
│   ├── genconfig.go            # `zk gen-config`: JWKS -> PEM -> kong.yml
│   ├── token.go                # `zk token`: credential -> access token
│   └── zitadel.go              # shared JWKS fetch + JWK->PEM
├── config/
│   ├── kong.tmpl.yml           # EDITABLE Kong config (services/routes/plugins)
│   └── service-key.json        # Zitadel service-user key (gitignored)
└── api/
    ├── docker-compose.yml      # API stack: just the backend           (project "sample-api")
    ├── Dockerfile
    ├── main.py                 # GET /api/hello -> {"message":"hello world"}
    └── requirements.txt
```

Topology: both Kong and the API attach to the external `edge` network. Kong
reaches the backend as `http://api:8000` (the API container's DNS alias on that
network). The API is **not** published to the host — the only way in is through
Kong on `:8000`, which enforces JWT auth.

## Prerequisites

1. The Zitadel stack is up: in `iam\zitadel`, `docker compose up -d --wait`,
   reachable at <http://localhost:8080>.
2. For the `curl` demo you need a **machine-to-machine credential**. In the
   Zitadel console, create a **Service User** (Users → Service Users → New),
   then:
   - **Set its `Access Token Type = JWT`** (edit the service user).
     _This is essential_ — machine users default to opaque **Bearer** tokens,
     which Kong's `jwt` plugin cannot verify (`Bad token; invalid JSON`). JWT
     tokens start with `eyJ`.
   - Give it a credential — either:
     - **Private Key JWT** (recommended): the service user → Keys → New → JSON,
       save it as `config/service-key.json`, and set `ZITADEL_KEY_FILE` in `.env`.
       The file's `"type"` must be `"serviceaccount"` (it has a `userId`) — an
       _application_ key will not work.
     - **Client secret**: generate a secret on the service user and set
       `ZITADEL_CLIENT_ID` / `ZITADEL_CLIENT_SECRET` in `.env`.

## Run

```sh
cp .env.example .env                                  # edit if your secret/issuer differ
docker network create edge                            # shared network (once)

docker compose -f api/docker-compose.yml up -d --build   # API stack
docker compose up -d --build                             # gateway stack (this dir)
```

(Or just run `./test.sh`, which creates the network, brings up both stacks, and
runs the smoke test.)

Order of events: `kong-init` waits for Zitadel's JWKS, renders `kong.yml`, exits
0; `kong` boots DB-less from it; the `api` stack serves the backend on the
`edge` network. Kong resolves the upstream by DNS at request time, so the two
stacks can start in any order.

- Kong proxy: <http://localhost:8000>
- Kong admin (read-only peek): <http://localhost:8001>
- The API has **no** host port — reach it only through Kong.

To stop: `docker compose down` (gateway) and
`docker compose -f api/docker-compose.yml down` (API).

## Multi-host (NetBird)

The single-host setup above relies on Docker's `edge` bridge network, which does
**not** span machines. To run Kong on one server and the API on another, NetBird
(a WireGuard mesh VPN) **replaces the `edge` network**: it gives every host an
encrypted overlay with a stable `100.x` IP and a DNS name. You stop addressing
the API by its Docker name (`api`) and start addressing it by its NetBird
identity.

What the `edge` network gave you, and the NetBird equivalent:

| Single host (Docker `edge`)     | Multi-host (NetBird)                          |
| ------------------------------- | --------------------------------------------- |
| Reachability between containers | Encrypted WireGuard mesh between **hosts**    |
| DNS name `api`                  | NetBird peer IP (`100.x`) or NetBird DNS name |
| Only Kong can reach the API     | NetBird **ACL policy** (peer/group rules)     |

Prereq: NetBird installed and joined on **both hosts** (the daemon runs on the
host, creating a `wt0` interface with a `100.x` IP). Verify with `netbird status`.

**1. Bring up the API on Host B in multi-host mode.** Use the ready-made
override `api/docker-compose.netbird.yml` — it publishes the port bound to the
NetBird IP and turns `edge` into a local bridge (no shared Docker network). Set
`API_NETBIRD_IP` to this host's IP from `netbird status`:

```sh
# on Host B
API_NETBIRD_IP=100.92.0.5 \
  docker compose -f api/docker-compose.yml -f api/docker-compose.netbird.yml \
  up -d --build
```

The base `expose`-only file is untouched, so the single-host `edge` setup keeps
working — the override is layered only when you want multi-host.

**2. Point Kong's upstream at the API's NetBird address.** `API_UPSTREAM` is
already an env var, so this is just `.env` on the **Kong host**:

```sh
# .env on Host A (Kong)
API_UPSTREAM=http://100.92.0.5:8000              # by NetBird IP
# or, preferred — survives re-provisioning, reads better:
API_UPSTREAM=http://apihost.netbird.cloud:8000   # by NetBird DNS name
```

Then re-render and reload Kong:

```sh
docker compose up --build kong-init && docker compose restart kong
```

**3. Lock it down (restore "only Kong can reach the API").** Publishing a port
means any mesh peer could hit it — use both:

- **NetBird ACL policy:** allow group `kong-host` → group `api-host` on `8000`,
  deny everything else. This is the real enforcement.
- **Bind to the VPN IP only** (the `100.92.0.5:8000:8000` above), so the API
  never listens on a public interface.

Notes:

- **Container → remote NetBird IP** works without extra config when NetBird runs
  on the host: the container's outbound traffic NATs through the host, which
  routes `100.64.0.0/10` via `wt0`. If your setup doesn't route the CGNAT range
  out of containers, run NetBird as a **sidecar inside the Kong container**
  (`netbirdio/netbird` image, `cap_add: [NET_ADMIN]`) so the container itself is
  a mesh peer.
- Prefer **NetBird DNS names** over raw IPs, and make sure the Kong host resolves
  them (enable NetBird DNS so its nameserver is used).
- Nothing about the **app-level contract** changes: Kong still validates the JWT
  at the edge and proxies to an upstream URL. Only the _meaning_ of that URL
  changes — a Docker DNS name on a local bridge becomes a NetBird IP/name on the
  VPN mesh. Going multi-host is an `.env` change plus publishing the API port; no
  code or template edits.

## Configuring Kong (rate limiting, CORS, more routes, …)

Kong runs **DB-less**, so all of its configuration lives in one declarative file.
You edit **`config/kong.tmpl.yml`** — `zk gen-config` renders it into the final
`kong.yml` (mounted into `kong-init`), substituting only three template values:

| Placeholder           | Filled with                                   |
| --------------------- | --------------------------------------------- |
| `{{ .Issuer }}`       | Zitadel issuer (and the jwt credential `key`) |
| `{{ .Upstream }}`     | the sample API upstream (`http://api:8000`)   |
| `{{ indent N .PEM }}` | Zitadel's RS256 public key, indented N spaces |

Everything else is plain Kong declarative config — add **services**, **routes**,
**consumers**, and **plugins** (scoped to a service/route/consumer, or global at
the bottom). `kong.tmpl.yml` ships with commented examples for `rate-limiting`,
`cors`, `request-transformer`, a second unauthenticated service, and global
`prometheus`/`correlation-id`. Plugin reference:
<https://docs.konghq.com/hub/> (use the OSS-tier plugins).

After editing, re-render and reload:

```sh
docker compose up --build kong-init   # re-render kong.yml from the template
docker compose restart kong           # load the new config
```

> The `jwt` plugin and the `zitadel` consumer credential are what enforce auth —
> keep them unless you intend to make a route public. To leave a route open, just
> don't attach the `jwt` plugin to it (see the `public-api` example).

To inspect what Kong actually loaded: `curl http://localhost:8001/` (config),
`curl http://localhost:8001/jwts` (registered keys).

## Try it

**1. No token → 401 (Kong blocks it):**

```sh
curl -i http://localhost:8000/api/hello
# HTTP/1.1 401 Unauthorized  {"message":"Unauthorized"}
```

**2. With a valid token → 200 from the backend.** Get a token with `zk token`
(reads `ZITADEL_CLIENT_ID`/`ZITADEL_CLIENT_SECRET` from the environment or
`-client-id`/`-client-secret` flags). Run it via the compose image (no Go needed)
or a local build:

```sh
# Via the already-built CLI image (no local Go toolchain required):
$tok = docker compose run --rm --no-deps `
  -e ZITADEL_CLIENT_ID=375478820087595011 -e ZITADEL_CLIENT_SECRET=$env:ZITADEL_CLIENT_SECRET `
  kong-init token --issuer http://host.docker.internal:8080
curl -H "Authorization: Bearer $tok" http://localhost:8000/api/hello
# {"message":"hello world","consumer":"zitadel","authenticated":true}
```

```bash
# Or build the binary once and use it directly (Linux/macOS/Windows):
go build -o zk ./cli
TOKEN=$(./zk token --client-id 375478820087595011 --client-secret "$ZITADEL_CLIENT_SECRET")
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/hello
```

## Authentication flow

```
            ┌─────────┐   1. login / grant     ┌──────────────────────┐
   client ──┤ Zitadel ├───────────────────────►│  access token (JWT)  │
            └────┬────┘   iss=http://localhost:8080
                 │
   (kong-init fetches JWKS once at startup, /oauth/v2/keys -> PEM)
                 │
            ┌────▼────┐   2. Bearer <jwt>      ┌──────────────────────┐
   client ──┤  Kong   ├──verify RS256 + exp───►│ 3. forward if valid  │
            │  :8000  │   key matched by `iss` │      to api:8000     │
            └─────────┘   else 401             └──────────┬───────────┘
                                                          ▼
                                           GET /api/hello -> hello world
```

1. Client obtains a JWT access token from Zitadel (browser Authorization-Code
   flow for users, or `client_credentials` for the curl demo).
2. Client calls Kong with `Authorization: Bearer <token>`. The `jwt` plugin
   looks up the credential by the token's `iss` claim, checks the RS256
   signature against the Zitadel PEM and that `exp` is in the future.
3. On success Kong forwards to the backend; otherwise it returns `401` and the
   backend is never reached.

### Getting a token in a browser (interactive users)

For real user login use the Authorization-Code + PKCE flow against
`http://localhost:8080/oauth/v2/authorize` with your app's redirect URI, then
exchange the `code` at `http://localhost:8080/oauth/v2/token`. Any resulting JWT
access token works against Kong identically to the curl demo above.

## Troubleshooting

| Symptom                                                           | Cause / fix                                                                                                                                                                                                                                                                 |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kong-init` loops "not ready" then fails                          | Zitadel isn't up or not on `:8080`. Start the `iam\zitadel` stack; verify <http://localhost:8080/.well-known/openid-configuration> loads.                                                                                                                                   |
| `401 {"Bad token; invalid JSON"}` / `Unauthorized` _with_ a token | Token is opaque, not a JWT (it starts with random chars, not `eyJ`). For a **service user**, set **Access Token Type = JWT** on the machine user (Users → Service Users → edit). For an interactive app, set the app's **Auth Token Type = JWT**. Then request a new token. |
| `401` "invalid signature"                                         | Zitadel rotated its signing key after `kong.yml` was generated. Refresh: `docker compose up --build kong-init` then `docker compose restart kong`.                                                                                                                          |
| `401` "no mandatory 'iss'..." / no credential                     | The token's `iss` doesn't equal `ZITADEL_ISSUER`. They must match byte-for-byte (scheme, host, port, no trailing slash).                                                                                                                                                    |
| `kong-init` can't reach Zitadel                                   | On Linux ensure `host.docker.internal` resolves (the compose file maps it to `host-gateway`). Alternatively set `ZITADEL_INTERNAL_URL` to your host IP. The `Host: localhost` header is required because Zitadel's Traefik routes on `Host(\`localhost\`)`.                 |
| `zk token` 400 `invalid_grant`/`unauthorized_client`              | The app doesn't allow `client_credentials`, or the secret is wrong. Use a machine user / API app that permits it, and pass `-client-secret` (or set `ZITADEL_CLIENT_SECRET`).                                                                                               |
| Want to inspect the generated config                              | `docker compose run --rm kong-init` regenerates it; `curl http://localhost:8001/jwts` shows the registered key.                                                                                                                                                             |
