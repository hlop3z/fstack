"""Minimal sample backend sitting behind Kong.

Kong terminates JWT validation, so this service trusts that any request it
receives is already authenticated. It also echoes the headers Kong (and any
upstream proxy like Cloudflare) injects so you can see who the caller is.
"""

import base64
import binascii
import json

from fastapi import FastAPI, Request

app = FastAPI(title="Sample API")

# Header prefixes/names injected by gateways/proxies, grouped for readability.
KONG_PREFIXES = ("x-consumer-", "x-credential-", "x-authenticated-", "x-anonymous-")
FORWARDED = (
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-forwarded-port",
    "x-real-ip",
    "forwarded",
)
CLOUDFLARE_PREFIX = "cf-"


@app.get("/api/hello")
def hello(request: Request):
    return {
        "message": "hello world",
        # Kong's jwt plugin forwards the matched consumer in these headers.
        "consumer": request.headers.get("x-consumer-username"),
        "authenticated": True,
    }


def _decode_jwt_claims(authorization: str | None) -> dict | None:
    """Decode (WITHOUT verifying) the claims of a Bearer JWT.

    Safe here only because Kong already verified the signature upstream. Never
    trust unverified claims in a service that is directly reachable.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    parts = token.split(".")
    if len(parts) != 3:
        return None  # opaque token, not a JWT
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError):
        return None


@app.get("/api/debug/headers")
def debug_headers(request: Request):
    """Show every header the backend received, grouped by who set it.

    curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/debug/headers
    """
    headers = {k.lower(): v for k, v in request.headers.items()}
    return {
        "client": {"ip": request.client.host if request.client else None},
        # Identity Kong attaches after validating the JWT.
        "kong": {k: v for k, v in headers.items() if k.startswith(KONG_PREFIXES)},
        # Hop/proxy headers (set by Kong, and by Cloudflare/LB if in front).
        "forwarded": {k: v for k, v in headers.items() if k in FORWARDED},
        # Cloudflare-specific (only present if Cloudflare actually proxied this).
        "cloudflare": {
            k: v for k, v in headers.items() if k.startswith(CLOUDFLARE_PREFIX)
        },
        # The JWT's claims (decoded from the still-forwarded Authorization header).
        "jwt_claims": _decode_jwt_claims(headers.get("authorization")),
        # Everything, verbatim.
        "all_headers": headers,
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
