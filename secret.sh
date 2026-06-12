#!/usr/bin/env sh
# Friendly wrapper for managing the fleet's infra secrets — so you never type the raw
# `docker compose run ... sops set ...` incantation. Operates on the target repo's
# infra/secrets/infra.sops.yaml via the console image (which has sops + the age key mounted).
#
# Run from the fstack directory:
#   ./secret.sh set <key>           # prompt for the value (HIDDEN — not echoed, not in history)
#   ./secret.sh set <key> <value>   # set inline (note: the value lands in your shell history)
#   ./secret.sh list                # list secret key names (no values)
#   ./secret.sh get <key>           # print one value (use sparingly; it goes to your terminal)
#   ./secret.sh rm  <key>           # delete a key
#
# Keys named *_token / *_key / *_webhook / *_password / *_secret are auto-encrypted by
# .sops.yaml. Any other name would store in PLAINTEXT, so `set` refuses it unless confirmed.
set -eu

# Relative to the console container's working dir (/work = the target repo). A relative
# path also avoids Git-Bash/MSYS rewriting a leading "/work" into a Windows path.
FILE="${INFRA_SECRET_FILE:-infra/secrets/infra.sops.yaml}"
DC() { MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' docker compose run --rm -T console "$@"; }

usage() { echo "usage: ./secret.sh {set <key> [value] | get <key> | rm <key> | list}" >&2; exit 2; }

cmd="${1:-}"; key="${2:-}"
case "$cmd" in
  list)
    DC sops -d "$FILE" | grep -E '^[A-Za-z0-9_]+:' | sed 's/:.*//' | sort
    ;;
  get)
    [ -n "$key" ] || usage
    DC sh -c "sops -d '$FILE' | python3 -c \"import sys,yaml;print(yaml.safe_load(sys.stdin).get('$key',''))\""
    ;;
  rm)
    [ -n "$key" ] || usage
    DC sops unset "$FILE" "[\"$key\"]"
    echo "✓ removed $key"
    ;;
  set)
    [ -n "$key" ] || usage
    case "$key" in
      *_token|*_key|*_webhook|*_password|*_secret) : ;;
      *)
        printf 'WARNING: "%s" is not a *_token/_key/_webhook/_password/_secret name — it would be stored in PLAINTEXT.\nContinue anyway? [y/N] ' "$key"
        read -r ans; [ "$ans" = y ] || { echo "aborted"; exit 1; } ;;
    esac
    if [ "$#" -ge 3 ]; then
      val="$3"
    else
      printf 'value for %s (hidden): ' "$key" >&2
      stty -echo 2>/dev/null || true
      read -r val
      stty echo 2>/dev/null || true
      echo >&2
    fi
    DC sops set "$FILE" "[\"$key\"]" "\"$val\""
    echo "✓ set $key (encrypted)"
    ;;
  ""|-h|--help) usage ;;
  *) echo "unknown command: $cmd" >&2; usage ;;
esac
