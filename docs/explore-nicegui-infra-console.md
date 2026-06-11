# Explore: Infra Console — a Python Dashboard as the Operator Entry Point (NiceGUI vs FastAPI + Alpine.js)

**Date:** 2026-06-10
**Status:** explorable idea (not yet a proposal)
**Builds on:** [ultra-think-infra-v2.md](./ultra-think-infra-v2.md)
**Idea:** Replace `Taskfile.yml` with a NiceGUI (Python) dashboard that lives next to Ansible — buttons to provision cells, run updates, rotate keys, refresh derived files, watch live playbook output. Python is already a hard dependency (Ansible runs on it), so the marginal runtime cost is zero.

---

## 1. The Idea, Restated Precisely

In the v2 design, the operator surface is:

```
Operator → Taskfile verbs → ansible-playbook / flux CLI
```

This idea changes it to:

```
Operator → NiceGUI console (localhost) → same ansible-playbook / flux / sops commands
                └── lives in infra/console/, same venv as Ansible
```

The console is a **toolkit for the basics**: provision a cell, patch hosts, rotate SSH keys, ping the fleet, regenerate derived files (inventory, schemas), stream playbook logs live, see Flux/cell health at a glance — all as buttons and panels instead of memorized verbs.

### Scope: the `infra` repo only — and where Terraform fits

This console + image is **L0/L1 tooling living in the `infra` repo, full stop.** The gitops repo (Flux roots, capabilities, apps — v2's L2) is a separate project with no console, no Docker, no Python in it: pure declarative YAML consumed in-cluster by Flux. The console's only contact with L2 is read-only status via mounted kubeconfigs — observation, never management. If a console feature ever needs the gitops repo *mounted*, that feature is out of scope by definition.

**What this stack actually replaces.** Calling it a Terraform substitute is close but worth sharpening, because Terraform and Ansible solve different problems:

- **Terraform** manages resource *acquisition* — calling a provider API to create/destroy VMs, DNS zones, buckets, and tracking them in a state file.
- **Ansible** configures machines that *already exist*.

Today, acquisition is manual ("old ways": buy a VPS in the Hostinger panel, get a fresh Ubuntu + root SSH). There is nothing for Terraform to *do* — adopting it now would mean importing hand-bought pets into a state file purely for ceremony, plus owning state-file storage/locking with zero churn to justify it. So the honest statement is: **the console + Ansible defers Terraform; it doesn't replace it.** Everything from first SSH onward is this stack's job, permanently.

**Terraform slots in *below* L0 later, as an acquisition layer (call it L-1), without moving anything above it.** The contract is already shaped for this: L0 consumes inventory entries (`host, IP, ssh_port, cell name`). Today `inventory.yml` is hand-authored — three lines for three VPSes. Under Terraform it becomes *generated* output (`terraform output -json` → a 20-line adapter → the same inventory schema). The console, the roles, the playbooks, the gitops repo: none of them change. Design rule to adopt **now** so that day is cheap: *nothing besides the inventory file may know where a host came from* — no Hostinger assumptions in roles or actions.

**The adoption trigger:** 9+ nodes is a fair proxy, but the real signal is **churn, not count**. A static fleet of 9 hand-bought VPSes still doesn't need Terraform; 5 cells that get created and destroyed monthly (cattle-cell DR, canary cells, per-client cells) do. Secondary triggers: a second provider, or wanting DNS zones/buckets in code. When it happens, note that Terraform *joins* Ansible rather than replacing it (Terraform: the VM exists; Ansible: the VM is configured) — and `terraform plan` / `apply` become two more danger-gated actions in the registry. The console design doesn't move. (Hostinger does expose a public API with a Terraform provider these days — verify its maturity when the day comes; if it's weak, OpenTofu/provider landscape is the thing to re-evaluate, not this architecture.)

## 2. The Tension to Resolve First (be honest about this)

The v2 doc's central thesis: _"every line of custom code is a liability with a bus factor of one"_ — it deletes a Go engine and a JS renderer. A dashboard is new custom code. So the idea only works if it obeys one hard rule:

> **The console is a remote control, not an engine.** It may _invoke_ the same commands the CLI would run. It may never _contain_ logic that doesn't exist outside it — no reconciliation, no state, no templating, no SSH of its own.

v1's Go platform manager started as exactly this kind of convenience layer and grew into a parallel brain with a SQLite ledger. The guardrails below exist to prevent the console from becoming **platform-manager v3 with a prettier face**.

**Invariant set (additions to v2's invariants):**

1. **CLI parity:** every button maps 1:1 to a command runnable by hand. Console dead → operations unaffected.
2. **Stateless:** the console holds no database, no ledger, no cache that matters. Kill the process, lose nothing.
3. **One writer per layer (unchanged):** Ansible writes L0/L1, Flux writes L2. The console writes _nothing_ — it only launches the writers and renders their output. Flux panels are **read-only**.
4. **Localhost only.** This process can launch root-SSH commands against the fleet. It binds `127.0.0.1`, is never deployed, never containerized-with-published-ports, never put behind "just a quick basic-auth."

## 3. Does Removing Taskfile Hold Up?

What Taskfile actually provides: (a) named verbs, (b) command composition, (c) discoverability, (d) a cross-platform runner. The console replaces (c) and (d) outright — buttons beat `task --list`, and Python is more Windows-native than anything in this stack. (a) and (b) must survive _outside the GUI_ or invariant 1 breaks.

**Resolution: extract the verb registry, share it between two thin frontends.**

```
infra/console/
├── actions.py     # THE registry: name → argv, target, danger, confirm  (~100 lines, plain data)
├── runner.py      # adapter: spawn process, stream lines, report exit   (~80 lines)
├── cli.py         # `python -m console run cell-update`                 (~40 lines, argparse)
└── app.py         # NiceGUI frontend over the same registry             (~250 lines)
```

Taskfile is then genuinely deletable: the registry _is_ the task file, in Python instead of YAML, and `cli.py` is the headless fallback (also what CI calls). One dependency removed (go-task), one added (NiceGUI). Net concept count: even — net capability: way up.

Verdict: **yes, removing Taskfile is sound** — but only with `cli.py` in the picture. GUI-only would make the dashboard a single point of operational failure, which is the platform-manager mistake again.

## 4. Architecture (fits v2's layers without modifying them)

The console is **operator tooling** — it sits _beside_ the layers, invoking downward-facing entry points only:

```
┌─────────────────────────────────────────────┐
│  infra/console (NiceGUI, localhost:8080)    │   reads: inventory.yml, kubeconfigs, git
│  fleet cards · action buttons · live logs   │   spawns: ansible-playbook, flux, sops, git
└──────┬──────────────────────────────────────┘
       │ subprocess only — no direct SSH, no k8s client library
       ▼
  ansible-playbook ─→ L0/L1 (hosts, k3s, flux bootstrap)
  flux / kubectl (read-only) ─→ L2 status panels
  sops ─→ secret edit ceremony helper
```

### Domain core (zero I/O, plain Python)

```python
@dataclass(frozen=True)
class Action:
    name: str                 # "cell:update"
    argv: tuple[str, ...]     # ("ansible-playbook", "playbooks/update.yml", "-l", "{cell}")
    params: tuple[str, ...]   # ("cell",) — rendered into argv, validated against inventory
    danger: Danger            # SAFE | DISRUPTIVE | DESTRUCTIVE
    description: str

class Danger(Enum):
    SAFE = auto()         # ping, status, render — one click
    DISRUPTIVE = auto()   # update, reconfigure — confirm dialog
    DESTRUCTIVE = auto()  # cell teardown — type-the-cell-name confirm (git-style)
```

Invariants enforced here: a param must resolve to a known inventory host/cell (no free-text into argv — this is also the command-injection guard); `DESTRUCTIVE` actions require typed confirmation. That's the _entire_ domain. Complexity O(actions) ≈ 15.

### Application layer

One use case: `run(action, params) → JobHandle` where a Job is a spawned process plus an async line-stream. One job at a time per target (a `dict[target, Job]` and a refusal, not a lock file — if two jobs race, that's the operator double-clicking, not a distributed-systems problem). Job history = an in-memory list, gone on restart, by design (invariant 2; the _real_ history is git log + Ansible output you already saw).

### Adapter layer

- `runner.py`: `asyncio.create_subprocess_exec` → line generator → `ui.log` push. No PTY needed (Ansible respects `ANSIBLE_FORCE_COLOR` + plain pipes).
- Status panels: `flux get kustomizations -A --no-header` / `kubectl get nodes` parsed leniently, refreshed by `ui.timer`. **Read-only by construction** — the console has no apply path.
- "Refresh files" buttons: spawn the same generators that exist as scripts (inventory derivation, schema gen, `format_markdown.py`). The button _is_ `subprocess.run([sys.executable, "scripts/gen_x.py"])`.

### UI sketch

```
┌ Fleet ────────────────────────────────────────────────┐
│ ● prod-a1  ssh ✓ k3s ✓ flux ✓ (2m ago)   [update] [verify]
│ ● prod-b2  ssh ✓ k3s ✓ flux ✗ drift      [update] [verify]
│ ○ canary-c1 unprovisioned                [provision…]
├ Actions ──────────────┬ Live output ────────────────────┤
│ [ping fleet]          │ TASK [base : ensure ufw rules]  │
│ [rotate ssh keys]  ⚠  │ ok: [prod-a1]                   │
│ [decrypt secrets]     │ changed: [prod-b2]              │
│ [regen inventory]     │ ▌streaming…                     │
└───────────────────────┴─────────────────────────────────┘
```

## 5. Dependency Justification (the v2 adapter-table treatment)

| Dependency                    | Why                                                                                     | Alternatives                                                                                                                                                    | Cost                                                                                                       | Verdict                                                                                    |
| ----------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **NiceGUI**                   | Buttons + live log streaming + timers in pure Python; no JS toolchain (the jkub lesson) | Textual (TUI — viable, zero browser, but no OneDrive-of-truth dashboards); Streamlit (rerun model fights log streaming); Flask+HTMX (more code, less batteries) | Pulls FastAPI/uvicorn (~15 transitive deps) into the _operator venv only_ — never on hosts, never in cells | **Accept** — this is the one place in v2 where a real dependency buys real daily-use value |
| **ansible-runner** (optional) | Structured per-task events instead of parsing stdout                                    | plain subprocess + stdout                                                                                                                                       | One more dep; richer UI                                                                                    | **Defer** — start with subprocess; adopt only if raw-log UX disappoints                    |
| **go-task**                   | —                                                                                       | —                                                                                                                                                               | —                                                                                                          | **Delete** (replaced by `actions.py` + `cli.py`)                                           |

NiceGUI version-pin discipline applies as everywhere else (`uv` lockfile in `console/`).

## 6. Variant: FastAPI + Alpine.js — Drop the Abstraction, Own the Thin Frontend

A key fact reframes this choice: **NiceGUI _is_ FastAPI + uvicorn underneath**, plus a Vue/Quasar component layer and a socket.io sync protocol on top. The variant keeps the bottom of that stack (which is boring and stable) and replaces the top (which is the fast-moving part) with ~200 lines you own.

Everything structural survives untouched — the registry, the runner, the CLI, all four invariants. The variant also sharpens the SoC inside the console itself: an **internal core** (pure Python, importable, zero HTTP awareness) and two thin **interface adapters** (CLI and HTTP) over it.

```
infra/console/
├── core/               # INTERNAL — pure Python, imports nothing from FastAPI
│   ├── actions.py      # the registry: the ONLY place the action surface is defined
│   ├── runner.py       # spawn + stream + exit code
│   └── jobs.py         # in-memory job table (dict), one job per target
├── cli.py              # interface adapter #1: argparse → core   (~40 lines)
├── app.py              # interface adapter #2: HTTP → core       (~100 lines, marshalling ONLY)
└── static/             # served by the same process
    ├── index.html      # one page, Alpine directives (~180 lines)
    ├── alpine.min.js   # vendored, ~15 kB, pinned by checksum — NO npm, NO build step
    └── pico.min.css    # vendored classless styling
```

**Dependency rule (the SoC line):** `core/` never imports `app.py` or `cli.py`; adapters never contain decisions. If `app.py` ever grows an `if action == ...` branch, logic has leaked out of the core — that's the violation alarm. Adding an action touches `core/actions.py` and *nothing else*: both interfaces pick it up automatically (the CLI from the registry dict, the page from `/api/state`).

### API shape: one write endpoint (and why not literally one endpoint)

The instinct "all in one POST for simplicity" is right where it matters — **all writes funnel through a single command endpoint**, RPC-style, so validation, danger-gating, and job creation happen at exactly one choke point, and the HTTP surface never grows when actions are added:

```
POST /api/run                {action, params}  → {job_id}     ← the ONLY route that can change anything
GET  /api/state              fleet + actions + jobs, one JSON  ← the page's single poll target
GET  /api/jobs/{id}/logs     SSE stream                        ← forced: EventSource can only GET
```

Three routes total, and going below three isn't possible or desirable:

- The log stream **must** be a separate GET — the browser's `EventSource` API cannot POST, and a long-lived stream multiplexed into a request/response endpoint would reinvent websockets badly.
- Folding reads into the POST ("command: status") would be a real loss, not a simplification: the GET/POST split encodes invariant 3 *at the protocol level* — anyone (including future-you) can see at a glance that exactly one route has side effects. Reads stay trivially cacheable, curl-able, and obviously safe.

```python
# app.py — marshalling only; every decision lives in core/
@app.post("/api/run")
async def run(cmd: RunCommand) -> dict:                # {"action": "cell:update", "params": {"cell": "prod-a1"}}
    job = core.run(cmd.action, cmd.params)             # core validates name+params, applies danger gate
    return {"job_id": job.id}

@app.get("/api/state")
async def state() -> dict:
    return core.snapshot()                             # fleet, actions registry, running jobs — one poll

@app.get("/api/jobs/{job_id}/logs")
async def logs(job_id: str) -> StreamingResponse:
    async def stream():
        async for line in core.jobs[job_id].lines():   # runner's existing generator
            yield f"data: {line}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")
```

```html
<!-- index.html -->
<div x-data="console_()">
  <button @click="run('fleet:ping')">ping fleet</button>
  <pre x-text="lines.join('\n')"></pre>
</div>
<script>
  function console_() { return {
    lines: [],
    async run(action, params = {}) {
      const r = await fetch("/api/run", { method: "POST", body: JSON.stringify({ action, params }) })
      const { job_id } = await r.json()
      new EventSource(`/api/jobs/${job_id}/logs`).onmessage = (e) => this.lines.push(e.data)
    },
  }}
</script>
```

Fleet status panels are `fetch` + `setInterval` against `/api/state` — one read endpoint, no sync framework needed for a read-only poll.

### Head-to-head

| Criterion              | NiceGUI                                                  | FastAPI + Alpine.js                                                           |
| ---------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Code you own           | ~250 lines, one language                                 | ~350 lines across Python + HTML/Alpine                                         |
| Dependency profile     | one fast-moving framework (Vue/Quasar/socket.io payload) | two boring commodities; Alpine vendored and frozen                             |
| Transparency           | magic Python↔DOM sync layer                              | plain HTTP + SSE — debuggable with curl and browser devtools                   |
| Churn risk over 5 yrs  | real: pin it, expect upgrade friction                    | near-zero: FastAPI is mature; Alpine v3 API stable since 2021                  |
| Time to first dashboard| hours                                                    | about a day                                                                    |
| Existing skills        | new framework API to learn                               | FastAPI already used (the fstack Zitadel+Kong api); Alpine is HTML attributes  |
| Byproduct              | none                                                     | a real JSON API: every button is also `curl -X POST :8080/api/run -d '{"action":"fleet:ping"}'`  |

Two notes on the byproduct API:

- It gives invariant 1 (CLI parity) a second free form — actions become scriptable over HTTP for ad-hoc automation.
- It must never become the argument for remote exposure. Invariant 4 is unchanged: `127.0.0.1` bind, no auth theater. The console launches root-SSH commands; an HTTP API makes that *easier* to accidentally expose, not safer.

### Which micro-library? (Alpine vs petite-vue vs Preact)

All three pass the no-toolchain test — each is a single vendorable file, no npm, no build. They differ on maintenance and on what kind of code they pull you toward:

| | Size (vendored) | Model | Maintenance status | Pull |
| --- | --- | --- | --- | --- |
| **Alpine.js v3** | ~15 kB | directives in HTML (`x-data`, `x-text`, `@click`) | actively maintained, large community, API stable since 2021 | stays sprinkle-on-HTML |
| **petite-vue** | ~6 kB | Vue template syntax subset (`v-if`, `@click`, `v-scope`) | **effectively frozen since ~2022** (v0.4.x, explicitly "not actively maintained") | stays sprinkle-on-HTML |
| **Preact (+ `htm` for no-build JSX)** | ~5 kB | real components, VDOM, hooks, app-shaped state | very actively maintained | pulls toward component architecture — and eventually toward a bundler |

- **Alpine** — the default pick. Maintained, documented, and *designed* for exactly this shape: a server-rendered page with a few reactive islands (a log pane, a fleet table). Its ceiling is low, which here is a feature.
- **petite-vue** — same shape, nicer syntax if you know Vue, half the size. The catch is maintenance: it shipped, froze, and its own author points people elsewhere. For a console you want to still work untouched in 2031, "frozen" cuts both ways — it will never break *or* be patched. Acceptable runner-up; vendor it and accept that you are its maintainer of last resort.
- **Preact** — the wrong tool *because* it is the most capable one. Components, hooks, and client-side state are what an *application* needs, and invariant 1 says the console must never become an application (the state lives in the registry and the processes, not the DOM). Most Preact workflows also assume npm/JSX; the no-build `htm` path works but swims against the ecosystem. Choosing Preact is choosing the gravity the guardrails exist to resist.

### The jkub-lesson check

v2's rule was "no JS toolchain in the infra loop." A vendored `alpine.min.js` static file involves **no toolchain**: no node, no package.json, no lockfile, no build step — it is an asset, like a CSS file. The line to hold: the moment the frontend wants a bundler, npm, or a component framework, stop — that is the signal the console is outgrowing "remote control," and the answer is to cut scope, not to add tooling.

## 7. Packaging: One Image, Compose as the Composition Root

Should ansible + the console ship as a single Docker image, with compose only attaching local folders and publishing the GUI? **Yes — and on this workstation it isn't even optional.** Ansible cannot run as a control node on Windows natively; v1 already runs it via `docker compose run ansible`. The v2 move is consolidation: v1 carries **three** toolchain images (`ansible`, `platform`, `sops`) — v2 needs exactly **one**, because the console, Ansible, and the secret tooling are all the same operator surface.

### The boundary statement

> **Image = toolchain. Mounts = state. Container = ephemeral.**
> The image holds everything *core* (pinned binaries + code) and nothing *live* (no secrets, no repo content, no state). It can be rebuilt, registry-pushed, even public.

Image contents, all version-pinned in one Dockerfile (digest-pinned base, per v1's existing discipline): Python + Ansible + console deps, `flux` CLI, `kubectl`, `sops`, `age`, `git`, `openssh-client`. That single Dockerfile becomes the **entire toolchain version surface** — upgrades are a one-file PR, testable and revertible.

```yaml
# compose.yml — composition root, nothing more
services:
  console:
    build: .                              # or image: ghcr.io/…/infra-console:0.1.0
    ports:
      - "127.0.0.1:8080:8080"             # loopback ONLY — compose's bare "8080:8080" binds 0.0.0.0 (violates invariant 4)
    volumes:
      - .:/work                           # infra repo (RW — playbooks, inventory, derived files)
      - ~/.infra/age:/keys/age:ro         # OUTSIDE the repo tree and OUTSIDE OneDrive
      - ~/.infra/ssh:/keys/ssh:ro
      - ~/.infra/kube:/kube:ro            # kubeconfigs for the read-only panels
    working_dir: /work
```

One image, three entrypoints — CLI parity (invariant 1) survives containerization:

```
docker compose up                                            # GUI at 127.0.0.1:8080
docker compose run --rm console cli run fleet:ping           # headless, same core/
docker compose run --rm console ansible-playbook playbooks/update.yml   # raw escape hatch
```

### Why this is CI-friendly

- CI pulls **the same image** the operator uses and runs the check suite (`ansible-lint`, `--syntax-check`, kustomize build, secrets lint). No "install ansible" steps in CI YAML that drift from the local toolchain — the class of "works locally, fails in CI" bugs disappears by construction.
- Operator-machine DR becomes trivial: Docker + `git clone` + restore the age/SSH keys = the full console, identical to the old machine.

### The drift to refuse

"CI/CD friendly" must not slide into **CI running playbooks against the fleet**. The line: CI *validates* (lint, check, build — needs no secrets), humans *execute* L0/L1 (via console or CLI), Flux *executes* L2. Handing CI the SSH key would create a third writer (violating v2 invariant 3) and put fleet-root credentials in a CI system — exactly the blast radius this redesign shrank. If push-from-CI ever becomes a real need, that's a new openspec change with its own threat model, not a convenience flag.

### Gotchas (small, real)

- **Loopback publish discipline** — the `127.0.0.1:` prefix in the ports entry is the guardrail; review it like a security control, because it is one.
- **known_hosts** — persist it via a mount (`~/.infra/ssh`), or every fresh container re-prompts/TOFUs on first connection.
- **Windows line endings** — enforce LF via `.gitattributes` (v1's UTF-8 discipline, extended); bind mounts on Docker Desktop are slower than native FS but irrelevant at this file count.
- **No hard Docker coupling in the code** — `core/` and `cli.py` are plain Python with zero Docker awareness, so a bare `uv venv` on any Linux box (or CI) remains a working fallback. The image is the *recommended* way to run, not the *only* way — keeping it that way is what makes it an asset instead of a dependency.

## 8. Trade-offs, Stated Plainly

**Gains**

- Discoverability: the fleet's entire operational surface visible on one screen; no memorized verbs. For a single operator returning after weeks away, this is the killer feature.
- Live, scrollback-friendly playbook logs beat terminal scroll; per-cell health at a glance merges `ping` + `flux get` + `kubectl get nodes` into one view.
- Guarded destructive actions (typed confirmation) — _safer_ than Taskfile, where `task destroy` and `task status` are one typo apart.
- One language for everything operator-side (Python already mandatory); Windows-friendly.

**Costs**

- ~450–500 lines of custom code to own (vs. ~100 lines of Taskfile YAML). Mitigated by: zero business logic inside it (invariant 1), boring stdlib + one framework.
- NiceGUI is a fast-moving project — pin it, expect occasional upgrade friction.
- Scope-creep gravity is _severe_: "add a SOPS editor", "add a kubectl apply button", "add a deploy panel" each individually reasonable, collectively platform-manager v3. The L2-read-only rule (invariant 3) is the line — **deploys stay `git push`**, the console at most shows whether Flux caught up.
- A browser process with fleet-root launch power on the workstation. Localhost-bind + no-auth-needed is correct _only_ while it stays localhost.

## 9. Where It Could Go Later (explicitly out of scope now — YAGNI)

- PR-style diff preview before `DISRUPTIVE` runs (`ansible-playbook --check --diff` in a panel) — actually cheap, probably the first v2 feature.
- Host-centric fleet board + tag-selected actions + ansible-runner structured events — designed in [explore-fleet-model-tags.md](./explore-fleet-model-tags.md); this is the console-v2 iteration once the spike verdict is in.
- A gitops panel that drafts the commit for you (still goes through git — doesn't violate invariant 3) — tempting, defer.
- Multi-operator/remote access → would require real auth (Zitadel OIDC, dogfooding) — a different product; do not slide into it.

## 10. Verdict

**The console idea is viable and a good fit — with the guardrails.** It is the rare custom-code candidate that passes v2's own test: it deletes a dependency (go-task), adds daily-felt operator value, contains zero logic that exists nowhere else, and is structurally incapable of becoming a second engine as long as the four invariants hold. The single biggest design decision is **`actions.py` + `cli.py` first, GUI second** — that ordering is what keeps it a remote control instead of a brain.

**Stack recommendation: FastAPI + vendored Alpine.js (§6), not NiceGUI.** NiceGUI optimizes time-to-first-dashboard; FastAPI + Alpine optimizes the criteria this repo actually selects for — boring commodity dependencies, five-year stability, total transparency (curl-debuggable HTTP + SSE), and skills already in the stack (the fstack Zitadel+Kong api was FastAPI). The cost is ~100 extra lines of HTML you own, and that trade goes the right way for a tool meant to outlive framework cycles. Among the micro-libraries, Alpine over petite-vue (maintained vs frozen) and over Preact (whose component model invites exactly the app-shaped growth the invariants forbid).

**Confidence:** medium-high. The remaining unknown is behavioral, not technical: whether the operator (you) actually reaches for a browser over a terminal day-to-day — worth a 1-day spike with 3 buttons (`ping`, `update`, live log) before committing the full design.

**Packaging (§7): one Docker image (ansible + console + flux/kubectl/sops toolchain), compose as the composition root** — repo and keys bind-mounted, GUI published on `127.0.0.1` only. This consolidates v1's three toolchain images into one, makes the Dockerfile the single toolchain-version surface, and lets CI run the exact operator image for validation. Hard line: CI validates, it never executes against the fleet.

**Suggested next step:** spike branch in `fstack` — `console/` with `core/` (registry with 3 actions + runner), `cli.py`, FastAPI `app.py` + one `index.html`, one Dockerfile + compose.yml; point it at ansible-01's existing playbooks read-only to feel the UX before infra v2 even lands.
