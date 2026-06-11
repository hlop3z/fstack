# Ultra-Think: Infra v2 — Replacing `ansible-01` with a Layered, Operable Platform

**Date:** 2026-06-10
**Subject:** Redesign of `~/Github/ansible-01` (mixed-concern infra monolith) into something far easier to operate and maintain, with real separation of concerns (SoC). Planning happens here in `fstack`.

---

## Context Snapshot (grounded in the actual repos)

**What `ansible-01` is today:**

| Concern                  | Implementation                                                                                  | State                                                                                    |
| ------------------------ | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Day-0 host provisioning  | 17 Ansible playbooks, **zero roles**, inline tasks                                              | Copy-pasted UFW rules in 4 places, god playbooks (`setup.yml` ~150 lines)                |
| Day-2 platform lifecycle | Custom Go CLI (`cmd/platform`, 8 packages) + SQLite ledger                                      | "Slated for retirement" but still the fallback                                           |
| GitOps                   | Flux (adopted 2026-06-09) + `jkub` JS rendering engine                                          | Two engines coexist; rendered tree committed to git                                      |
| Spec                     | `cluster.yml` single source of truth                                                            | Mixes nodes, capabilities, apps, DNS, TLS, middleware in one file                        |
| Secrets                  | SOPS + age                                                                                      | Works, but decrypt→edit→encrypt→clean ceremony; Cloudflare token in plaintext `.env`     |
| Workloads                | k3s on 3 Hostinger KVMs; CNPG Postgres, Garage S3, RabbitMQ, Redis, Zitadel, Prometheus/Grafana | 2-node stretched cluster over 66 ms WAN; fleet-of-cells migration planned but unfinished |
| Dead weight              | WireGuard flannel backend (abandoned), wg0 mesh (black-holes traffic), `rancher-detach.yml`     | Experimental code + 250-word gotcha prose still in config                                |

**Operator:** one person. That is the single most important constraint in this entire analysis.

---

# Phase 1: First-Principles Decomposition

## Invariants (true regardless of implementation)

1. **Desired state must live in git, encrypted where secret.** SOPS+age already satisfies this; keep it.
2. **Convergence must be idempotent and observable.** Running the same operation twice must be safe, and "is reality == spec?" must be answerable with one command.
3. **Exactly one engine owns each layer.** The current pain is two engines (SSH platform manager + Flux) owning Day-2 simultaneously. An invariant of v2: no layer has two writers.
4. **A fresh machine → running cell must be reproducible** from git + one offline secret (the age key). Everything else is derived.
5. **Pinned versions everywhere** (already done well in v1 — digest-pinned images, vendored charts). Preserve this discipline.
6. **The cluster topology is fleet-of-cells**: independent single-node k3s cells (prod-a1, prod-b2, …), not stretched clusters over 66 ms links. v1 already learned this lesson the hard way (etcd at 70–120 ms commit latency); v2 bakes it in as an invariant.

## Boundaries

The system decomposes into **four layers with one-way dependencies** (each layer consumes only the output of the layer below, never reaches back down):

```
L3  Apps            (app source repos — already separate; out of scope)
L2  Workloads       (what runs in each cell: platform services + app deployments)
L1  Cluster         (k3s + Flux + secrets-decryption installed and pointed at L2)
L0  Host            (OS hardened, firewall, SSH, swap, unattended-upgrades)
```

The system **ends** at: app source code (separate repos), DNS registrar/Cloudflare account creation (manual, one-time), Hostinger VM purchase (manual). It **begins** at: a fresh Ubuntu VM with root SSH.

## Contracts (the interfaces between layers)

| Boundary       | Contract                                                                                        | Format                                                                |
| -------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| L0 → L1        | "A hardened host reachable on SSH port X"                                                       | Inventory entry (host, IP, role)                                      |
| L1 → L2        | "A k3s API + Flux running, SOPS age key as in-cluster Secret, watching git path P"              | Flux `GitRepository` + `Kustomization` pointing at `clusters/<cell>/` |
| L2 → apps      | "Postgres/S3/Redis/MQ reachable at well-known in-cluster DNS names; OIDC at Zitadel issuer URL" | Kubernetes `Service` names + injected `Secret`s                       |
| Operator → all | One task runner with layer-prefixed verbs                                                       | `task host:provision`, `task cell:bootstrap`, `flux reconcile`        |

## Unknowns (assumptions made; flagged for validation)

- **U1:** "SOC" = separation of concerns (from "we mixed everything in a single repo"), not SOC-2 compliance. Assumed.
- **U2:** The fleet-of-cells direction (from v1's roadmap) is still desired. Assumed yes — it also dramatically simplifies v2 (no multi-node Ansible choreography, no WireGuard mesh, no stretched etcd).
- **U3:** Single operator, no team. Assumed from git history.
- **U4:** The Go platform manager's Day-2 features (reconcile/deploy/dns/render) are fully replaceable by Flux + plain manifests + a tiny DNS sync. Assumed — Flux adoption completed 2026-06-09, so this is nearly proven.
- **U5:** Zitadel + Kong (the deleted `fstack` experiment) is the intended ingress/auth pattern for v2, replacing raw Traefik middleware. Open question, not assumed.

---

# Phase 2: Abstraction-Layer Analysis

## Domain Core (zero dependencies)

The domain of this system is small. Strip away the tooling and the **core types** are:

```
Cell        = { name, host: Host, channel: Channel }            # one VM = one k3s cell
Host        = { addr: IpAddr, ssh_port: u16, ssh_key_ref }      # value object
Channel     = stable | canary                                    # which gitops overlay it tracks
Capability  = postgres | s3 | redis | mq | oidc | monitoring     # closed enum, per-cell on/off
AppBinding  = { app, cell, domain, needs: Set<Capability> }
```

**Domain invariants (pure rules, no I/O):**

- A `Cell` has exactly one `Host` (single-node by definition — this _deletes_ the worker-join, mesh, and stretched-etcd problem space).
- An `AppBinding.needs ⊆ Cell.capabilities` — an app cannot bind to a cell missing its dependencies. (v1 enforced this in Go's `needs resolution`; v2 enforces it structurally: the app's kustomization lives inside the cell's directory, so a missing capability fails at `kustomize build` time, i.e. in CI, not at runtime.)
- State transitions are git commits. There is **no other state machine.** v1's SQLite ledger existed because the SSH engine needed idempotency memory; Flux's reconciliation loop makes desired-vs-actual comparison continuous, so the ledger is deleted, not migrated.

**Complexity:** the domain is O(cells × capabilities) ≈ 3 × 6 = trivial. Any design that introduces super-linear complexity here (cross-cell coordination, global locks, mesh topology O(n²) peer pairs — v1's WireGuard mesh was exactly this) is over-engineering. **The strongest typing win available is not a programming language at all — it is directory structure + kustomize + CI validation**, which gives "compile-time" guarantees (PR fails to build) with zero code to maintain.

## Application Layer (use cases)

The complete verb set an operator needs:

| Use case               | v1 implementation                              | v2 implementation                                                        | Critical path complexity             |
| ---------------------- | ---------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------ |
| Provision new cell     | `task provision` (8 chained steps, Ansible+Go) | `task cell:new -- prod-c3` → 1 Ansible run + 1 Flux bootstrap            | O(1) per cell, ~10 min               |
| Deploy/change workload | decrypt → edit → encrypt → `platform deploy`   | git commit → Flux reconciles                                             | O(1), zero local ceremony            |
| Rotate a secret        | SOPS ceremony + redeploy                       | edit `.sops.yaml` blob → commit → Flux + SOPS-operator decrypts          | O(1)                                 |
| Drift check            | `platform status` (custom Go)                  | `flux get all -A` / `kubectl diff`                                       | built-in                             |
| DNS sync               | `platform dns` (custom Go, Cloudflare API)     | external-dns controller in-cluster, or 50-line script                    | O(apps)                              |
| Patch OS               | `update.yml`                                   | unattended-upgrades (already configured) + occasional `task host:update` | O(cells), embarrassingly parallel    |
| Disaster recovery      | undocumented                                   | `task cell:new` + restore CNPG backup from S3                            | O(1) per cell — **cells are cattle** |

**CQRS suitability:** not applicable as a pattern to implement — but GitOps _is_ CQS: writes are git commits (commands), reads are `flux get`/Grafana (queries). Transaction boundary = one git commit = one atomic reconciliation unit. Idempotency comes free from Kubernetes server-side apply.

**Data structures:** none worth naming. The "database" is a git tree; the access pattern is `kustomize build` (a tree fold, O(files)). This is the point — the application layer should contain **no code requiring complexity analysis.**

## Adapter Layer (infrastructure — all I/O, each dependency justified)

| Dependency                                                         | Why needed                                                                                                        | Alternatives considered                                                                                                      | Cost                                                                         | Verdict                                                                                                         |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Ansible (small)**                                                | Day-0 only: idempotent OS config over SSH; mature, agentless                                                      | cloud-init (Hostinger support is weak/inconsistent for re-runs); shell scripts (not idempotent); Pyinfra (smaller ecosystem) | Already known; ~3 roles                                                      | **Keep, shrink to L0 only**                                                                                     |
| **k3s**                                                            | Single-binary Kubernetes, perfect for 1-node cells                                                                | plain Docker Compose (loses Flux/Helm/CNPG ecosystem); full k8s (overkill)                                                   | Already proven in v1                                                         | **Keep**                                                                                                        |
| **Flux**                                                           | The single Day-2 engine; reconcile loop, Helm + kustomize native, SOPS decryption built into kustomize-controller | ArgoCD (heavier, UI-centric, SOPS needs plugins); keep Go manager (custom code, one maintainer)                              | Already adopted (2026-06-09)                                                 | **Keep, make it the _only_ engine**                                                                             |
| **SOPS + age**                                                     | Secrets in git, one offline key                                                                                   | Vault (a server to operate — absurd for one person); sealed-secrets (key lives in-cluster, harder DR)                        | Already in use                                                               | **Keep**                                                                                                        |
| **Task (go-task)**                                                 | Operator entry point                                                                                              | Make (Windows-hostile); just (fine, but Task is incumbent)                                                                   | Already in use                                                               | **Keep, reorganize verbs by layer**                                                                             |
| **external-dns** (optional)                                        | Cloudflare A-record sync from Ingress annotations                                                                 | keep 50 lines of the Go `dns` package as a script                                                                            | One more controller per cell                                                 | Either; **prefer external-dns** (deletes custom code)                                                           |
| **DELETED: Go platform manager**                                   | —                                                                                                                 | —                                                                                                                            | 30 files, 8 packages, SQLite ledger, an entire parallel brain                | **Delete**                                                                                                      |
| **DELETED: jkub renderer**                                         | —                                                                                                                 | —                                                                                                                            | A custom templating engine is a second programming language for one consumer | **Delete** — hand-author kustomize overlays; with ≤3 cells, base+overlay duplication is cheaper than a compiler |
| **DELETED: WireGuard mesh, worker-join playbooks, rancher-detach** | —                                                                                                                 | —                                                                                                                            | Dead/abandoned                                                               | **Delete**                                                                                                      |

Dependency direction is clean: nothing above L1 knows about Hostinger, SSH, or Ansible; nothing in gitops knows how the host was provisioned.

---

# Phase 3: Multi-Perspective Evaluation

## Technical Lens

**Language fit** — ranked for the ~200 lines of glue that survive (validation scripts, secret gen, optional DNS sync):

1. **Go** — only if any long-running component survives (it shouldn't). Single static binary was v1's Go argument; with the platform manager deleted, the argument evaporates.
2. **Python (stdlib-only)** — best fit for the actual remaining need: short, run-once validation/generation scripts. `fstack/scripts/gen_secret.py` already sets the convention (stdlib-only, CLI+library). Ubiquitous on every host.
3. **Rust** — maximal safety for zero remaining problems that need it. The system's correctness lives in YAML + reconciliation, not in code.
4. **TypeScript** — jkub proved the cost: a node toolchain in the infra loop for templating YAML. Avoid.

**The real answer is "as little language as possible":** YAML (declarative spec) + ~3 Ansible roles + ≤300 lines of stdlib Python. Every line of imperative code in v1 (Go engine, jkub) is a line v2 refuses to own.

**Performance:** irrelevant at this scale (3 cells, 1 app, reconcile loops measured in seconds). The only "hot path" is _operator time_, and the bottleneck is ceremony: v1's deploy = decrypt→edit→encrypt→deploy→clean (5 steps); v2's deploy = commit→push (2 steps). That is the performance win that matters.

## Architectural Lens

**SOLID, applied to infrastructure:**

- **SRP:** each repo/layer has one reason to change. Host hardening changes → `infra` repo. Workload changes → `gitops` repo. App changes → app repo. v1 violated this totally — `cluster.yml` changed for every reason.
- **OCP:** adding a cell = adding a directory under `clusters/` + one inventory line. No existing file is modified except the inventory. Adding a capability to a cell = adding one kustomize resource reference.
- **LSP:** every cell is substitutable — same base, differing only in overlay values. Canary channel is a cell like any other.
- **ISP:** apps consume narrow contracts (a Secret with a DSN; an issuer URL), never the cluster spec.
- **DIP:** Flux (high-level policy) depends on the git abstraction, not on hosts. Ansible never reaches above L1.

**Patterns that apply (and the rest don't):**

- **Template Method / base+overlay** (kustomize): the one pattern doing real work. Cell = base + thin overlay.
- **Observer**: Flux watching git _is_ the observer pattern; no need to build one.
- **Strategy** at the channel level: `stable` vs `canary` overlays.
- Factory/Builder/Decorator/Prototype: no justification — would be speculative architecture. YAGNI.

**Clean architecture check:** dependency arrows all point inward (host → cluster → workloads → apps consume downward contracts only). v1's worst violation — Ansible running `kubectl` over SSH (`security-netpol.yml`), a Day-0 tool writing Day-2 state — becomes structurally impossible: NetworkPolicies are Flux-managed manifests.

## Pragmatic Lens

- **KISS:** v2 is _less_ total machinery than v1 (deletes ~30 Go files, jkub, SQLite, 9 of 17 playbooks) while doing the same job.
- **YAGNI:** no multi-node cells, no mesh, no custom renderer, no Vault, no service mesh (the old README's Kong→Envoy diagram) until an actual requirement appears.
- **DRY:** v1's real duplication (UFW rules ×4) is fixed with one `firewall` role. But base+overlay YAML "duplication" across 3 cells is **similarity, not duplication** — resist the urge to rebuild jkub. The rule: reach for a generator only when cells > ~10 or overlays drift apart in ways kustomize can't express.
- **Operational reality:** one person, Windows authoring (UTF-8 discipline already documented), OneDrive-synced checkout (note: keep age keys _out_ of OneDrive). Debuggability: `flux get` + Grafana replaces "read the Go source to learn what reconcile does." Bus factor improves from "only the author understands jkub+Go engine" to "anyone who knows Flux understands everything."

---

# Phase 4: Solutions

## Approach A — "Two Repos, Zero Engines" (boring GitOps split)

**Abstraction model:**

```
repo: infra/                          # L0 + L1 — changes rarely
├── inventory.yml                     # hand-authored, tiny: 3 hosts, cell names
├── roles/
│   ├── base/          # apt, SSH hardening, fail2ban, sysctl, swap, unattended-upgrades
│   ├── firewall/      # UFW — ONE place (fixes the ×4 duplication)
│   └── k3s_cell/      # single-node k3s install + flux bootstrap + age-key secret
├── playbooks/
│   ├── cell.yml       # provision a cell end-to-end (the only entry point)
│   ├── update.yml     # OS patching
│   └── ssh-rotate.yml # key rotation (keep — it works)
└── Taskfile.yml       # task cell:new, task host:update, task ssh:rotate

repo: gitops/                         # L2 — changes often; THE deploy surface
├── clusters/
│   ├── prod-a1/       # Flux Kustomization root per cell
│   ├── prod-b2/
│   └── canary-c1/
├── platform/          # base + per-capability components (cnpg, garage, redis, mq, zitadel, monitoring)
│   ├── base/
│   └── components/    # kustomize components — a cell opts in per capability
├── apps/
│   └── dufeut-site/   # base + per-cell overlay; SOPS-encrypted secrets adjacent
└── .sops.yaml
```

Contract between repos: `k3s_cell` role ends by installing Flux pointed at `gitops//clusters/<cell>/`. Nothing else crosses the boundary.

- **Language:** YAML + Ansible; ≤300 lines stdlib Python for validation/CI.
- **Dependencies:** Ansible, k3s, Flux, SOPS+age, Task, (external-dns). All already in use except external-dns.
- **Complexity:** provision O(1)/cell; deploy O(1); the whole system O(cells × capabilities).
- **Trade-offs:** ✚ near-zero custom code, every tool is industry-standard, structural SoC (repo = layer), cattle-cell DR. ✛ kustomize overlay verbosity; two repos to clone; no single `cluster.yml` overview (mitigated by a README table).

## Approach B — "Spec Compiler, Done Right" (cluster.yml v2 → rendered gitops)

Keep v1's best idea — one declarative `fleet.yml` — and build a _small, disciplined_ compiler (Go, ~500 lines, schema-validated) that renders the gitops tree in CI. Operator edits only `fleet.yml`; CI commits the rendered tree; Flux consumes it.

- **Language:** Go (schema via struct tags, single binary in CI).
- **Dependencies:** everything in A **plus** the compiler you now own forever.
- **Trade-offs:** ✚ one-file fleet overview, DRY across many cells, typo-proof. ✛ this is jkub/platform-manager again with better hygiene; rendered-tree-in-git problem returns (v1 pain #6); debugging means reading compiler source. **Justified only at >10 cells or multi-tenant.** Right idea, wrong year.

## Approach C — "No Kubernetes" (Compose-per-cell radical simplification)

Each cell = Docker Compose + systemd; Ansible deploys compose files; secrets via SOPS-rendered env files. Kong DB-less fronts each cell (reusing the deleted `fstack` Zitadel+Kong experiment directly).

- **Language:** YAML + Ansible only. **Lowest concept count of all three.**
- **Trade-offs:** ✚ no k8s to understand; the fstack experiment slots right in. ✛ loses CNPG (operator-managed Postgres + S3 backup/restore is v1's most valuable production asset), loses Flux drift correction (Ansible push model returns — drift between runs), loses vendored-chart ecosystem; rebuilds backup/health/restart logic by hand. **Net: deletes the platform's crown jewels to save a learning curve already climbed.**

---

# Phase 5: RECOMMENDATION

**Approach:** A — "Two Repos, Zero Engines"

**Language:** YAML (declarative core) + Ansible (L0/L1) + stdlib Python ≤300 lines (glue/CI)

**Core abstractions:**

- `Cell` — one VM, one single-node k3s, one Flux root (`clusters/<name>/`)
- `Role` ×3 — `base`, `firewall`, `k3s_cell` (all host logic, deduplicated)
- `Capability` — kustomize component a cell opts into (`platform/components/<cap>`)
- `AppBinding` — app overlay referenced from a cell's kustomization
- Layer contract: L0/L1 ends at "Flux watching `clusters/<cell>/`"; L2 never looks down

**External dependencies:**

- Ansible (Day-0 only), k3s, Flux, SOPS + age, Task, external-dns (optional, replaces custom DNS code)
- **Deleted from v1:** Go platform manager (8 pkgs/30 files), jkub, SQLite ledger, WireGuard mesh, worker-join playbooks, rancher-detach — roughly half the repo's moving parts

**Complexity:**

- Time: O(1) per operator action (deploy = git push); O(cells) for fleet-wide ops, embarrassingly parallel
- Space: O(cells × capabilities) YAML ≈ trivial at 3×6; no runtime state outside k8s itself (ledger deleted)

**Confidence:** high

**Reasoning:** Every hard decision was already made and paid for in v1 — Flux is adopted, SOPS works, k3s is proven, the fleet-of-cells lesson is learned (66 ms etcd). v2 is not a rewrite; it is a **deletion plus a reorganization**. The two-repo split makes separation of concerns structural rather than disciplinary: it is _impossible_ for a playbook to deploy a workload or for an app change to touch host config, because the files live in different repos with different change cadences. For a single operator, every line of custom code is a liability with a bus factor of one; Approach A drives custom code to ~zero while keeping the production-grade assets (CNPG backups, monitoring, pinning discipline) intact.

# WHY NOT THE OTHERS

**Approach B (spec compiler):** It rebuilds the exact machinery whose maintenance burden triggered this redesign — jkub and the Go renderer — with better engineering hygiene but the same ownership cost. The single-file-overview benefit is real but only pays off past ~10 cells. Keep it in the back pocket; the gitops repo layout in A is compiler-friendly if that day comes.

**Approach C (no Kubernetes):** Optimizes the wrong variable. The k8s learning curve is sunk cost; CNPG-managed Postgres with S3 backup/restore, Flux drift correction, and the vendored chart ecosystem are working production assets that Compose would force you to rebuild by hand, badly. Simplicity that deletes your disaster-recovery story is not simplicity.

# IMPLEMENTATION ORDER

1. **Define domain types and interfaces** — write `openspec` specs in fstack: the Cell/Capability/AppBinding model, the L0→L1→L2 contracts, repo boundaries (this doc is the input).
2. **Define domain rules and invariants** — CI checks: `kustomize build` all cells, SOPS encryption lint (no plaintext secrets), schema check on inventory. Fail-fast at PR time.
3. **Implement application use cases** — author the `gitops` repo: migrate v1's _rendered_ `gitops/` tree (already Flux-consumed since 2026-06-09) into hand-authored base+components+overlays. This is reorganization, not rewriting.
4. **Implement infrastructure adapters** — author the `infra` repo: distill 17 playbooks into 3 roles + 3 playbooks; the firewall role kills the ×4 duplication on day one.
5. **Compose at the root** — `task cell:new` end-to-end: Ansible → k3s → Flux bootstrap → cell converges from git. Test by provisioning a fresh canary cell _before_ touching prod.
6. **Tests and observability** — `verify.yml` becomes a smoke-test task; Flux alerts → existing Alertmanager; Grafana dashboard per cell.
7. **Deploy and validate** — migrate prod cells one at a time (cattle: provision new cell, restore CNPG backup, flip DNS, retire old). Then **archive `ansible-01` read-only** — no half-migrated limbo, which is v1's current disease (two engines, two topologies coexisting).

# RISKS AND MITIGATIONS

**Risk:** Migration stalls midway, leaving three repos and two engines (worse than today).
**Mitigation:** Step 7's cell-by-cell cutover with hard archive date; the canary cell (step 5) proves the full path before prod moves. v1 stays untouched-but-frozen until the last cell flips.

**Risk:** Kustomize overlay sprawl recreates duplication as cells grow.
**Mitigation:** kustomize _components_ for capabilities (opt-in composition, not copy-paste); revisit Approach B only past ~10 cells.

**Risk:** Losing the Go manager's validation (`needs` resolution, schema) regresses safety.
**Mitigation:** CI `kustomize build` catches dangling references structurally; a 50-line Python lint can encode any remaining semantic rule.

**Risk:** age key loss = total secret lockout (single offline key).
**Mitigation:** Already mitigated in v1 (offline backup); add a second recipient key stored separately. Keep keys out of the OneDrive-synced tree.

**Risk:** external-dns mismanages Cloudflare records (it owns what it creates).
**Mitigation:** Run with `--policy=upsert-only` initially; or keep v1's DNS logic as a 50-line standalone script (it's the one piece of the Go manager worth salvaging).

---

# Phase 6: Meta-Analysis

**Potential biases:**

- _Incumbency bias:_ keeping Ansible/k3s/Flux/SOPS because they're already there. Counterweight: each was independently justified in the adapter table; still, B and C were evaluated seriously and C would win if k8s knowledge were zero.
- _Anti-code bias:_ the analysis treats custom code as pure liability. For a single operator that's nearly always right, but it undervalues B's typo-prevention at larger scale.

**Constraint sensitivity:**

- **Team of 3+ engineers** → Approach B's compiler becomes maintainable; reconsider at that point.
- **Cells > 10 or multi-tenant** → B's single-spec overview starts paying; the A layout migrates into B cleanly (the gitops tree becomes the compiler's output format).
- **Budget forces fewer/cheaper VMs** → C (Compose) re-enters; the fstack Kong+Zitadel experiment is its ready-made ingress.
- **Node churn (cells created/destroyed routinely, or ~9+ nodes, or a second provider)** → add an acquisition layer *below* L0 (Terraform/OpenTofu): VMs, DNS zones, buckets in code; `inventory.yml` flips from hand-authored to generated output. Nothing above L0 changes — provided the rule "only the inventory file knows where a host came from" is held from day one.
- **Compliance (real SOC-2)** → audit logging, access review, and change-approval gates change the gitops repo (protected branches, signed commits) but not the architecture.

**Weakest areas (lowest confidence):**

- Whether hand-authored kustomize stays pleasant at even 3 cells × 6 capabilities — verbosity is real; confidence medium.
- external-dns vs. salvaged DNS script — minor either way.
- U5 (Kong+Zitadel as the v2 ingress/auth layer vs. v1's Traefik+middleware) is genuinely undecided and deserves its own openspec change.

**Additional information that would most improve confidence:**

1. Confirm fleet-of-cells is still the target topology (U2) — it underpins the entire single-node simplification.
2. Confirm the Flux-rendered tree currently in `ansible-01/gitops/` is complete (does anything still require the SSH platform manager?). If yes, step 3 is mostly a `git mv`.
3. Decide repo granularity preference: two repos (recommended) vs. one repo with `infra/` + `gitops/` top-level dirs (acceptable; Flux can watch a subpath — but the SoC then relies on discipline instead of structure).
4. The Kong/Zitadel ingress question (U5).

---

_Next step in fstack: turn this into an OpenSpec change (`opsx:propose`) covering the two-repo layout, the L0–L2 contracts, and the migration plan as task lists._

_Refinement (2026-06-10): the Host/Tag/selector fleet model, the everything-k3s decision (mgmt plane becomes a cell, NetBird in-cluster, Coolify retired), and the ansible-runner trigger are explored in [explore-fleet-model-tags.md](./explore-fleet-model-tags.md) — fold these into the spec when proposing._
