# Design: infra-console-spike

## Context

`docs/ultra-think-infra-v2.md` defines the infra v2 architecture (layered L0–L2, Ansible for hosts, Flux for workloads, two repos). `docs/explore-nicegui-infra-console.md` designs a browser console as the operator entry point and settles the stack debate (FastAPI + vendored Alpine.js over NiceGUI; single Docker image; compose as composition root). This change implements the **spike** that both docs call for: the minimal console pointed read-only at `ansible-01`'s existing playbooks, to answer the one remaining unknown — does a browser console actually beat the terminal for day-to-day single-operator use — before infra v2 lands and before Taskfile removal is committed to.

Constraints inherited from the explore doc (binding, not advisory):

1. **CLI parity** — every button is a runnable command; GUI dead → operations unaffected.
2. **Stateless** — no DB, no ledger; job history is in-memory and dies with the process.
3. **Console writes nothing** — it spawns the writers (Ansible) and renders output; L2 is untouched in the spike (no flux/kubectl panels yet).
4. **Localhost only** — the process can launch root-SSH; it binds `127.0.0.1`, no auth theater.
5. **Interface vs internal SoC** — `core/` never imports adapters; adapters contain no decisions.

## Goals / Non-Goals

**Goals:**

- A working dashboard + CLI with exactly 3 actions (`fleet:ping`, one more SAFE read action, `host:update` in `--check` mode), live SSE logs, and danger-gated buttons.
- One Docker image (Python + Ansible + console), compose wiring with loopback-only publish and read-only key mounts.
- Enough real UX to make the Taskfile-replacement decision with evidence.

**Non-Goals:**

- Removing Taskfile from `ansible-01`, or modifying `ansible-01` at all.
- The infra v2 repo split, gitops repo, or any Flux/kubectl integration (even read-only panels — deferred past the spike).
- SOPS/secrets workflows, auth, remote access, HTTPS, job persistence, multi-operator anything.
- Terraform/acquisition layer (separate future concern, below L0).

## Decisions

### D1: Layout — `core/` internal, two adapters, one page

```
console/
├── core/
│   ├── actions.py    # registry: Action(name, argv, params, danger, description); 3 entries
│   ├── runner.py     # asyncio.create_subprocess_exec → async line iterator + exit code
│   ├── jobs.py       # in-memory dict; one running job per target; busy → refusal
│   └── inventory.py  # parse target repo inventory → closed set of valid hosts/groups
├── __main__.py       # python -m console → cli
├── cli.py            # argparse: list | run <action> [k=v...]; exit code = job exit code
├── app.py            # FastAPI: POST /api/run, GET /api/state, GET /api/jobs/{id}/logs (SSE), static mount
└── static/
    ├── index.html    # Alpine directives; state poll + run + SSE log pane
    ├── alpine.min.js # vendored, pinned by checksum
    └── pico.min.css  # vendored
```

Rationale: the explore doc's interface-vs-internal rule made concrete. The import direction is testable (CI can assert `core/` imports cleanly without FastAPI installed).

### D2: FastAPI + vendored Alpine.js, not NiceGUI

Decided in the explore doc §6 and not relitigated here: NiceGUI is FastAPI underneath plus a fast-moving sync layer; owning ~200 lines of HTML buys boring commodity dependencies, curl-debuggability, and five-year stability. Alpine over petite-vue (maintained vs frozen) and over Preact (component model invites app-shaped growth the invariants forbid).

### D3: Three routes, RPC-style single write endpoint

`POST /api/run` is the only write — one choke point for validation/danger-gating/job creation, and the HTTP surface never grows when actions are added. Reads stay GET (`/api/state` as the page's single poll target) because the verb split encodes "exactly one route has side effects" at the protocol level. The SSE log route is forced to be separate (browser `EventSource` can only GET). Alternative considered: literally one endpoint with a `command` field — rejected; it erases the read/write distinction for zero simplification.

### D4: Subprocess + stdout parsing, not ansible-runner

Start with `asyncio.create_subprocess_exec` and raw lines (`ANSIBLE_FORCE_COLOR=0`, `PYTHONUNBUFFERED=1`). `ansible-runner` gives structured per-task events but adds a dependency before the spike proves the UX matters at all. Revisit only if raw-log readability disappoints.

### D5: Param validation = closed-set membership against the inventory

Parameters render into argv templates only if the value is a known inventory host/group (loaded by `core/inventory.py` from the mounted target repo). This is simultaneously the correctness check and the command-injection guard — no quoting/escaping logic to get wrong, because free text never reaches argv. No shell is ever invoked (`exec`, not `sh -c`).

### D6: Packaging — image = toolchain, mounts = state

Single Dockerfile (digest-pinned `python:3.12-slim` base; `uv`-installed pinned deps; ansible + openssh-client). Compose publishes `127.0.0.1:8080:8080` and mounts: target repo at `/work` (rw), SSH keys read-only from outside the repo tree (not under OneDrive). Entrypoint dispatches: no args → uvicorn; `cli ...` → CLI; anything else → exec verbatim (the escape hatch). The image contains zero secrets and is registry-pushable.

### D7: Spike targets `ansible-01` as-is

Actions wrap `ansible-playbook playbooks/ping.yml` and `playbooks/update.yml --check` with `ansible-01` mounted. Nothing in that repo changes; its `ansible.cfg`/inventory are consumed as found. This keeps the spike honest (real fleet, real playbooks, real latency) while staying risk-free.

## Risks / Trade-offs

- **[Spike code calcifies into the product without review]** → The spike lives in `fstack` (not `ansible-01`, not the future `infra` repo); promotion to infra v2 is a deliberate later change with its own proposal.
- **[Loopback guarantee silently broken by a compose edit]** → The `127.0.0.1:` ports prefix is spec-level (console-packaging); add a comment in `compose.yml` marking it a security control; verify from a second device once during the spike.
- **[Ansible output buffering makes "live" logs chunky]** → Set `PYTHONUNBUFFERED=1` and `ANSIBLE_FORCE_COLOR=0`; if Ansible still block-buffers under pipes, accept per-task chunk granularity for the spike (it answers the UX question anyway) and note ansible-runner as the fix.
- **[Windows bind-mount quirks (line endings, file perms on keys)]** → Enforce LF via `.gitattributes`; mount keys from a dedicated `~/.infra/` directory; document `icacls`-equivalent expectations in the README if SSH complains about key permissions inside the container.
- **[Inventory parsing scope creep]** → `core/inventory.py` reads only what validation needs (host/group names) via `ansible-inventory --list` subprocess, not a YAML parser of our own — Ansible itself is the inventory authority.

## Migration Plan

Not applicable (new, additive, isolated). Rollback = delete `console/`, `Dockerfile`, `compose.yml`. The spike's success criteria feed the *next* change (console adoption in infra v2 + Taskfile removal), which is where any migration would live.

## Open Questions

- Does live raw-log streaming feel good enough, or is `ansible-runner`'s structured event stream needed? (Answer comes from using the spike.)
- The behavioral question itself: after two weeks, is the browser the default reach, or did the CLI win? Define the success signal loosely as "the console was the chosen interface for most fleet checks/updates during the spike period."
- Second SAFE action choice: `fleet:facts` (ansible setup module summary) vs `inventory:show` (render parsed inventory). Decide at implementation; zero architectural impact.
