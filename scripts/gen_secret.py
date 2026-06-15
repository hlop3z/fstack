#!/usr/bin/env python3
"""Generate cryptographically-secure passwords / secrets (stdlib only).

Uses the `secrets` module (CSPRNG). The default `password` type guarantees at least
one lowercase, uppercase, digit, and symbol — enough for strict policies like
strict validators. Symbols are restricted to a shell/YAML/URL-friendly set (no quotes,
backslash, backtick, or spaces) so values paste safely into env files and configs.

Examples:
  gen_secret.py                      # one 32-char complexity password
  gen_secret.py -l 24 -n 5           # five 24-char passwords
  gen_secret.py --no-symbols         # alphanumeric only
  gen_secret.py -t hex -l 64         # 64 hex chars (e.g. a 32-byte key)
  gen_secret.py -t base64 -l 44      # url-safe base64 token
  gen_secret.py -t uuid              # a UUIDv4

Importable too:  from gen_secret import password; password(32)
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys
import uuid

# Symbols safe to paste into shells, .env files, YAML, and URLs unquoted.
SAFE_SYMBOLS = "!@#$%^&*()-_=+[]{}.,:?"
_RNG = secrets.SystemRandom()


def password(length: int = 32, *, symbols: str = SAFE_SYMBOLS) -> str:
    """Return a random password with at least one char from each enabled class."""
    classes = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
    if symbols:
        classes.append(symbols)
    if length < len(classes):
        raise ValueError(f"length must be >= {len(classes)} to include every class")
    pool = "".join(classes)
    chars = [secrets.choice(c) for c in classes]  # guarantee one of each
    chars += [secrets.choice(pool) for _ in range(length - len(chars))]
    _RNG.shuffle(chars)
    return "".join(chars)


def hex_token(length: int = 64) -> str:
    """Return `length` hex characters (length/2 random bytes)."""
    return secrets.token_hex((length + 1) // 2)[:length]


def base64_token(length: int = 43) -> str:
    """Return `length` URL-safe base64 characters."""
    tok = ""
    while len(tok) < length:
        tok += secrets.token_urlsafe(length)
    return tok[:length]


def generate(kind: str, length: int, *, use_symbols: bool = True) -> str:
    match kind:
        case "password":
            return password(length, symbols=SAFE_SYMBOLS if use_symbols else "")
        case "hex":
            return hex_token(length)
        case "base64":
            return base64_token(length)
        case "uuid":
            return str(uuid.uuid4())
        case _:
            raise ValueError(f"unknown type: {kind}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="gen_secret.py",
        description="Generate secure passwords/secrets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="types: password (default) | hex | base64 | uuid",
    )
    p.add_argument("-t", "--type", default="password",
                   choices=["password", "hex", "base64", "uuid"],
                   help="kind of secret to generate (default: password)")
    p.add_argument("-l", "--length", type=int, default=32,
                   help="output length in characters (ignored for uuid; default: 32)")
    p.add_argument("-n", "--count", type=int, default=1,
                   help="how many to generate (default: 1)")
    p.add_argument("--no-symbols", action="store_true",
                   help="password type: use letters + digits only")
    args = p.parse_args(argv)

    if args.length < 1:
        p.error("--length must be >= 1")
    if args.count < 1:
        p.error("--count must be >= 1")

    try:
        for _ in range(args.count):
            print(generate(args.type, args.length, use_symbols=not args.no_symbols))
    except ValueError as e:
        p.error(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
