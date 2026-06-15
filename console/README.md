# infra console (spike)

Operator dashboard + CLI over Ansible. A remote control, **not** an engine: it
invokes the same commands you would run by hand, and contains no logic that
exists nowhere else. Design + rationale: `docs/explore-nicegui-infra-console.md`,
spec: `openspec/changes/infra-console-spike/`.

## Run (recommended: Docker — required on Windows, Ansible can't control-node there)

```sh
docker compose up --build          # dashboard at http://127.0.0.1:8080
```

Keys: the entrypoint stages them to `/root/.ssh` with chmod 600 (Windows bind
mounts surface 0644, which ssh rejects). Source order: `~/.infra/ssh` mount if
non-empty (override with `CONSOLE_KEYS`), else the target repo's `config/ssh/`.

Port 8080 taken on the host (e.g. another service)? `CONSOLE_PORT=8090 docker compose up`
— still loopback-only.

Same image, headless:

```sh
docker compose run --rm console cli list
docker compose run --rm console cli run fleet:ping
docker compose run --rm console cli run host:update host=web-01
docker compose run --rm console ansible-playbook playbooks/update.yml --check   # raw escape hatch
```

Target repo defaults to `../target-repo`; override with `CONSOLE_TARGET=path docker compose up`.

## Run (bare venv fallback, Linux/macOS)

```sh
uv sync && uv run python -m console serve        # binds 127.0.0.1:8080
CONSOLE_TARGET_DIR=../target-repo uv run python -m console run fleet:ping
```

## Tests

```sh
uv run python -m unittest discover tests -v
```

## The five invariants (binding — a PR that breaks one is wrong by definition)

1. **CLI parity** — every button maps 1:1 to a runnable command; GUI dead → operations unaffected.
2. **Stateless** — no DB, no ledger; job history is in-memory and dies with the process.
3. **Console writes nothing** — it spawns the writers (Ansible) and renders output. Deploys stay `git push`/Flux.
4. **Localhost only** — the `127.0.0.1:` prefix in `compose.yml` ports is a security control. No auth theater, no remote exposure.
5. **Interface vs internal** — `console/core/` never imports FastAPI/uvicorn; adapters (`cli.py`, `app.py`) contain no decisions. Tripwire: an `if action == ...` in an adapter means logic leaked.

Adding an action = one entry in `core/actions.py`. Both interfaces pick it up automatically.

## Spike success signal

After the trial period, answer honestly: **was the console the chosen interface
for most fleet checks/updates?** Record the verdict in
`docs/explore-nicegui-infra-console.md` §10 — adopt into infra v2 (+ Taskfile
removal, as a new openspec change) or stay CLI-only.
