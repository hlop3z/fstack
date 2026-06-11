# Proposal: infra-console-spike

## Why

The infra v2 plan (`docs/ultra-think-infra-v2.md`) replaces a mixed-concern Ansible monolith with a layered design, and the explore doc (`docs/explore-nicegui-infra-console.md`) proposes a browser console as the operator entry point — but its biggest unknown is behavioral, not technical: will a single operator actually reach for a browser over a terminal day-to-day? This spike answers that question cheaply, by building the minimal console (3 actions, 3 HTTP routes, 1 page) pointed read-only at `ansible-01`'s existing playbooks, before infra v2 lands and before Taskfile is removed.

## What Changes

- New `console/` Python package in `fstack`: an operator dashboard + CLI for running Ansible playbooks with live log streaming.
  - `console/core/` — internal layer, pure Python, zero HTTP/Docker imports: action registry (3 actions), async subprocess runner with line streaming, in-memory jobs table.
  - `console/cli.py` — argparse adapter over `core/` (headless parity with the GUI).
  - `console/app.py` — FastAPI adapter over `core/`, exactly 3 routes: `POST /api/run` (the only write), `GET /api/state`, `GET /api/jobs/{id}/logs` (SSE).
  - `console/static/` — one `index.html` with vendored `alpine.min.js` + `pico.min.css`; no npm, no build step.
- New `Dockerfile` (single image: Python + Ansible + console) and `compose.yml` (loopback-only port publish `127.0.0.1:8080`, bind mounts for target repo + SSH keys).
- The spike targets `ansible-01`'s existing playbooks (`ping.yml`, `update.yml`) without modifying that repo.
- Non-goals (explicitly out of scope): Taskfile removal, the infra v2 repo split, any L2/gitops write path, secrets (SOPS) handling, auth, remote access, job persistence.

## Capabilities

### New Capabilities

- `console-core`: action registry with danger levels and param validation, async job runner with live line streaming, in-memory job table — the internal layer both interfaces consume.
- `console-cli`: headless command-line interface over the core (list actions, run an action, stream its output) proving CLI parity.
- `console-api`: localhost HTTP interface — one write route (`POST /api/run`), one read route (`GET /api/state`), one SSE log-stream route — plus the static dashboard page served by the same process.
- `console-packaging`: single Docker image (Ansible + console toolchain) with compose as the composition root: loopback-only publish, read-only key mounts, target repo bind mount.

### Modified Capabilities

<!-- none — openspec/specs/ is empty; this is the first change in the repo -->

## Impact

- **New code:** `console/` (~500 lines Python + ~200 lines HTML), `Dockerfile`, `compose.yml` — all in `fstack`.
- **Dependencies added:** FastAPI + uvicorn (operator venv/image only); vendored static assets (Alpine.js, Pico CSS) pinned by checksum.
- **External systems:** runs `ansible-playbook` against the `ansible-01` fleet (read-only actions only in this spike: ping, plus `--check`-mode update); reads its inventory. No writes to `ansible-01` files, no k8s/Flux interaction in the spike.
- **Security surface:** a localhost-bound process able to spawn root-SSH commands. Guardrail invariants from the explore doc are binding: CLI parity, stateless, console writes nothing, `127.0.0.1` only, no Docker coupling in `core/`.
- **Decision this spike feeds:** whether the console replaces Taskfile as the operator entry point in infra v2 (a later, separate change).
