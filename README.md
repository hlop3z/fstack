# console

A small, **repo-agnostic operator console** — a dashboard + CLI that runs *your*
target repo's declared actions (Ansible, SOPS secrets, shell) behind a confirmation
gate. It holds no fleet logic of its own: the target repo declares its action and
secret surface in `console.actions.yml`; the console just runs them.

## Run

```sh
docker compose up        # dashboard at http://127.0.0.1:8080  (loopback only)
```

Point it at the repo it should operate on:

```sh
CONSOLE_TARGET=../your-repo docker compose up
```

- **Actions** — declared in the target repo's `console.actions.yml`; the dashboard
  renders a card per action with typed params and a confirmation gate by danger level.
- **Secrets** — manifest-driven SOPS: `console secret set|get|edit` plus a
  localhost-only browser editor (ephemeral plaintext, leak-guarded, derived re-renders).
- **CLI** — `docker compose run --rm console cli <…>` or `python -m console <…>`.

Loopback-only by design (`serve` binds `127.0.0.1`) — it can launch privileged
commands. The image is published to a registry; consumers run it against their own
repo via their own `compose.yml`. See [`console/README.md`](console/README.md).
