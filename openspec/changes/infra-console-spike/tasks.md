# Tasks: infra-console-spike

## 1. Scaffolding

- [x] 1.1 Create `console/` package: `core/` subpackage, `__main__.py`, `cli.py`, `app.py`, `static/`; add `pyproject.toml` with pinned FastAPI + uvicorn (uv-managed)
- [x] 1.2 Vendor `static/alpine.min.js` (pinned release) and `static/pico.min.css`; record versions + checksums in a comment header or `static/VENDORED.md`
- [x] 1.3 Add `.gitattributes` enforcing LF for `console/`, `Dockerfile`, `compose.yml`

## 2. Core (internal layer — no FastAPI imports)

- [x] 2.1 `core/actions.py`: `Danger` enum, frozen `Action` dataclass, registry with 3 actions — `fleet:ping` (SAFE), second SAFE read action (decided: `inventory:show` — pure local read, no SSH), `host:update` wrapping `update.yml --check` (DISRUPTIVE)
- [x] 2.2 `core/inventory.py`: load valid host/group names via `ansible-inventory --list` subprocess against the mounted target repo
- [x] 2.3 `core/runner.py`: `asyncio.create_subprocess_exec` (never shell) with `PYTHONUNBUFFERED=1`, `ANSIBLE_FORCE_COLOR=0`; async line iterator; exit-code capture
- [x] 2.4 `core/jobs.py`: in-memory job table, one running job per target (busy → refusal), terminal states `succeeded`/`failed`
- [x] 2.5 Core entry point `core.run(action, params)`: registry lookup → param validation against inventory (closed set, reject anything else) → danger gate → spawn job
- [x] 2.6 Tests: unknown action rejected; injection-shaped param rejected; busy target refused; `core/` imports cleanly with FastAPI uninstalled (import-isolation test) — 8 tests passing via `python -m unittest`

## 3. CLI adapter

- [x] 3.1 `cli.py`: `list` (name, danger, description) and `run <action> [k=v...]` streaming lines to stdout, process exit code = job exit code; wire `__main__.py`
- [x] 3.2 Confirmation flag pass-through for DESTRUCTIVE actions (gate enforced in core; CLI stays non-interactive) — covered by `DangerGateTests` core test

## 4. HTTP adapter + dashboard

- [x] 4.1 `app.py`: `POST /api/run` → `{job_id}`; `GET /api/state` → registry + fleet + jobs in one JSON; `GET /api/jobs/{id}/logs` → SSE; error mapping (400 validation / 409 busy / 404 unknown job / 503 inventory unavailable); static mount at `/`; uvicorn bound to `127.0.0.1`
- [x] 4.2 Verify the marshalling-only rule: no action-name branching in `app.py` (grep check: only the docstring tripwire matches)
- [x] 4.3 `static/index.html`: Alpine page — fleet/action/jobs rendering from `/api/state` poll (`setInterval` fetch), run buttons posting to `/api/run`, confirm dialog for DISRUPTIVE, typed-name prompt for DESTRUCTIVE, SSE log pane with autoscroll
- [x] 4.4 Smoke-test with curl: state JSON ✓, run + SSE stream ✓, 400 unknown-action ✓, 404 unknown-job ✓, 503 inventory-unavailable ✓ (found+fixed a 500 leak), static page ✓; 409 busy verified at core-test level

## 5. Packaging

- [x] 5.1 `Dockerfile`: digest-pinned `python:3.12-slim` (`sha256:090ba77e…`), pinned ansible-core 2.18.6 + openssh-client + console; `docker-entrypoint.sh` dispatch (no args → uvicorn on 0.0.0.0 inside container; `cli` → CLI; else exec verbatim); zero secrets/keys/repo content in image
- [x] 5.2 `compose.yml`: ports `"127.0.0.1:8080:8080"` (commented as security control); mounts: `${CONSOLE_TARGET:-../ansible-01}` at `/work` (rw), `~/.infra/ssh:/root/.ssh:ro`, working_dir `/work`
- [x] 5.3 Confirm all three entrypoints from compose: `up` (GUI ✓, on `CONSOLE_PORT=8090` — host 8080 was taken), `run --rm console cli run fleet:ping` ✓ (both hosts pong), `run --rm console ansible-playbook playbooks/ping.yml` ✓. Found+fixed two Windows-mount issues: ansible.cfg ignored in world-writable `/work` (now `ANSIBLE_CONFIG` env) and 0644 key perms (entrypoint stages keys to `/root/.ssh` chmod 600)
- [ ] 5.4 Verify loopback isolation from a second device: **host-side verified** (`docker ps` shows `127.0.0.1:8090->8080`; `Get-NetTCPConnection` LocalAddress `127.0.0.1`, not `0.0.0.0`) — remaining: one 30-second check from another LAN device

## 6. End-to-end against ansible-01 + spike evaluation

- [x] 6.1 Run `fleet:ping` and `host:update` (`--check`) end-to-end against the real fleet from the dashboard's API path and from the CLI ✓ — `host:update host=srv1.internal` streamed a full check-mode playbook over SSE (recap ok=4 changed=2 dry-run, exit 0); 409 busy-path verified live; `git status` in ansible-01: CLEAN
- [x] 6.2 Log streaming assessed: live at per-task/per-host granularity (timestamped lines arrive as produced; within-block lines burst together, which is Ansible's own output shape). Verdict: good enough — `ansible-runner` not needed for the spike; revisit only if long plays feel opaque in the browser during the trial
- [x] 6.3 Write `console/README.md`: run instructions (compose + bare-venv fallback), the five guardrail invariants, and the spike's success signal
- [ ] 6.4 After the trial period: record the verdict (adopt into infra v2 + Taskfile removal as a new change, or stay CLI-only) in `docs/explore-nicegui-infra-console.md` — **trial period**
