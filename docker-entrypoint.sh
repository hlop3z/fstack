#!/bin/sh
# Entrypoint dispatch — one image, three modes:
#   (no args)       -> GUI server. 0.0.0.0 is container-internal; exposure is
#                      controlled by compose's loopback-only port publish.
#   cli ...         -> headless CLI (python -m console ...)
#   anything else   -> exec verbatim (raw escape hatch, e.g. ansible-playbook ...)
set -e

# Stage SSH keys into the container with sane permissions. Windows bind mounts
# surface as 0644/0755, which OpenSSH rejects for private keys — so we copy
# (container-local, ephemeral; the image itself still contains no keys).
# Preferred source: /keys/ssh mount; fallback: the target repo's config/ssh.
for src in /keys/ssh "${CONSOLE_TARGET_DIR:-/work}/config/ssh"; do
    if [ -d "$src" ] && [ -n "$(ls -A "$src" 2>/dev/null)" ]; then
        mkdir -p /root/.ssh
        cp -L "$src"/* /root/.ssh/ 2>/dev/null || true
        chmod 700 /root/.ssh
        chmod 600 /root/.ssh/* 2>/dev/null || true
        break
    fi
done

if [ $# -eq 0 ]; then
    exec python -m console serve --host 0.0.0.0 --port 8080
fi

if [ "$1" = "cli" ]; then
    shift
    exec python -m console "$@"
fi

exec "$@"
