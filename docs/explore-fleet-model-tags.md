# Explore: Hosts + Tags Fleet Model, Everything-k3s, and the ansible-runner Trigger

**Date:** 2026-06-10
**Status:** explorable idea (feeds infra v2 specs; console v2 follows from it)
**Builds on:** [ultra-think-infra-v2.md](./ultra-think-infra-v2.md), [explore-nicegui-infra-console.md](./explore-nicegui-infra-console.md)
**Trigger:** the console spike made v1's inventory mess visible — the fleet view shows six groups that are all the same two servers under different names, and the third server (`clouder`: NetBird control plane + Coolify + Gitea + Zot) isn't in the picture at all.

---

## 1. The Diagnosis: v1's Groups Conflate Membership with Role

v1's derived inventory has `k3s_cache_nodes`, `k3s_database_nodes`, `k3s_queue_nodes`, `k3s_storage_nodes`, `k3s_control_plane`, `k3s_workers` — six groups, two servers. Those groups exist only because the retired Go platform manager selected hosts per capability. Ansible groups are being used to encode *what runs on a host* (a workload concern, L2) inside *the host list* (an infra concern, L0). That's the SoC violation, and it's why the fleet view reads as noise.

The fix is the user's instinct stated precisely: **hosts and actions are separate concerns; a host carries tags; actions select by tag.**

## 2. The Model

```yaml
# fleet.yml — the whole fleet, hand-authored, one screen
hosts:
  srv1:    { addr: 31.220.54.40,  tags: [cell] }
  srv2:    { addr: 72.62.161.127, tags: [cell] }
  clouder: { addr: 72.62.170.85,  tags: [cell, canary] }   # mgmt becomes just another cell
```

```
Host   = { name, addr, ssh_port, tags: set[Tag] }
Action = { name, argv, selector: Tag | all, danger }       # console derives eligible hosts
Tag    = host-level trait ONLY: cell, canary, ufw-provider, …
```

- **Action × selector replaces action × hardcoded group.** `host:update` selects `all`; `k3s:install` selects `cell`; a future `ufw:provider-mode` selects `ufw-provider`. Attaching behavior to a new host = adding a tag — exactly the "easy to attach to any host" property asked for.
- **Ansible mapping is mechanical:** one generated group per tag (a 20-line inventory plugin/template away). No hand-maintained group lists, no group explosion.
- **The console UI consequence:** the Fleet tab becomes the primary board — one row per *host* with tag chips and per-host status lights; picking an action filters eligible hosts by selector. The current group-spam list disappears because the groups disappear.

### The line that keeps this honest (important)

Tags are for **L0/L1 host traits only** — does k3s go on it, which channel, who manages the firewall. **What workloads run on a cell stays in the gitops repo** (the cell's kustomization referencing capability components), *not* in tags.

Why so strict: if tags also declared workloads (`tags: [postgres, s3, oidc]`), something would have to translate tags → manifests — and that something is the spec compiler (v2's rejected Approach B / jkub reborn) sneaking in through the back door. The two views stay separate and small: `fleet.yml` says *which machines exist and what kind they are*; `gitops/clusters/<cell>/` says *what runs there*. A README table gives the combined overview for humans.

## 3. Everything-k3s: Make `clouder` a Cell, Run NetBird Inside

**Yes — uniformity wins, with one dependency rule.**

Current state: `clouder` is a snowflake — Docker Compose stacks (NetBird control plane, Coolify, Gitea, Zot) managed by different playbooks than everything else. Making it a k3s cell means: one host shape fleet-wide, one provisioning path (`cell.yml`), one deploy model (Flux), one backup pattern (CronJobs instead of `netbird-backup.yml`), one monitoring story. The mgmt-plane playbooks (`netbird-backup.yml`, the `services/netbird` compose tree) get deleted, not migrated.

**The dependency rule that makes it safe:** the NetBird cell must be recoverable *without* NetBird. Check against reality:

- Ansible SSHes to **public IPs** (per inventory), not through the mesh → provisioning/recovery path independent of NetBird ✓
- Flux must pull from a git remote *not* hosted on this fleet (GitHub, not the local Gitea) — **verify this before migrating**; if gitops lives on Gitea-on-clouder, that's a circular dependency and the remote moves to GitHub first.
- DR = the same cattle-cell story: `task cell:new` over public SSH + restore NetBird state from S3. The mesh being down during recovery is fine because nothing in the recovery path uses it.

**Coolify: retire it.** In the target architecture its job doesn't exist — deploys are `git push` + Flux, and its PaaS conveniences duplicate what the gitops repo already does. One less always-on service with root-adjacent powers on the mgmt host.

**Gitea/Zot: removed** (decided 2026-06-10). GitHub is the gitops source of truth, so Gitea duplicates it for no one; Zot has no consumer worth its upkeep. Neither migrates to the cell — they get backed up once (export anything worth keeping), then deleted with the compose stack.

### NetBird migration order: backup-first, restore-proven

NetBird's identity/state is the one thing on `clouder` that cannot be regenerated — losing it means re-enrolling every peer. The move is therefore gated on a **proven restore**, not just a backup:

1. **Backup now, before anything else** — ✅ DONE 2026-06-11: `netbird-identity-srv1244743-20260611T024558Z.tar.gz` (sha256 `85ca2f4d…`) verified by S3 round-trip (download + content listing: store.db/idp.db/events.db + config.yaml with enc key + compose + dashboard.env) and held in TWO places: `s3://dufeut-bk/netbird-state/srv1244743/` and locally at `~/.infra/backups/`. Bonus: `clouder-final-snapshot-20260611T025006Z.tar.gz` (WordPress DB dump + wp-content, sha256 `cd1a7fb7…`) in `s3://dufeut-bk/clouder-final/` + `~/.infra/backups/` — Gitea was confirmed empty; Coolify-hosted WordPress snapshotted just in case. Root cause of v1's "S3 403-then-retry" gotcha identified along the way: the `backups` IAM user lacks bucket-level perms, so rclone needs `--s3-no-check-bucket` (and still logs one 403 before succeeding).
2. **Prove the restore** — ✅ DONE 2026-06-11, in production: clouder was wiped (Debian 13), hardened via `setup.yml`, Docker CE installed, and NetBird restored from the backup (identity dbs seeded into the volume, config restored, standalone-Traefik compose replacing the dead Coolify proxy — see `fstack/interim/netbird-clouder/`). Both srv1 and srv2 peers reconnected with their pre-wipe identities (Management/Signal Connected), and the mesh data plane verified: srv1→srv2 over `wt0` 0% loss @ 64 ms. Backup timer reinstalled on the fresh OS; first new-OS backup verified (`…032403Z.tar.gz`). Notes for the cluster build: clouder itself has no netbird *client* yet (only the control plane in Docker) — the CP node joins the mesh during k3s provisioning; the store still carries the dead pre-wipe clouder peer entry (prune via dashboard).
3. **Freeze changes** — no peer enrollments/ACL edits during the migration window (the backup is the cutover snapshot).
4. **Provision `clouder` as a cell** (or a fresh cell) and deploy NetBird via Flux; **restore the state** into the in-cluster instance before exposing it.
5. **Cut over and watch** — peers reconnect against the same domain/endpoints; only after the mesh is green do Coolify/Gitea/Zot and the compose stack get deleted.
6. **Re-point the backup** — the CronJob replacement for `netbird-backup.yml` goes live in the same change; the first in-cluster backup is verified the same way as step 1.

Rollback at any point before step 5 = the old compose stack is still running, untouched.

## 4. ansible-runner: the Calculus Changed

The spike's verdict was "raw stdout is good enough — defer." That verdict assumed single-host, one-job-at-a-time actions. The tags model breaks that assumption:

- A tag-selected action (`host:update` → `all`) is inherently **multi-host**; raw stdout interleaves per-host results into one stream.
- The fleet board wants **per-host outcomes** (srv1 ✓, srv2 ✗, clouder running…) — that requires structured events, not text parsing.
- ansible-runner emits exactly this: `runner_on_ok` / `runner_on_failed` / `playbook_on_task_start` events as JSON, per host, while still providing the raw stdout for the transmission pane.

So: **adopt ansible-runner in console v2** (the post-spike iteration), not as polish but as the enabler of the host-centric board. Two integration notes:

- **Statelessness invariant holds:** runner wants a `private_data_dir` where it writes artifacts; point it at an ephemeral temp dir per job and delete on completion. No ledger returns.
- The runner event stream slots into the existing `core/runner.py` seam — the adapters and routes don't change; `jobs.py` grows per-host status alongside the line buffer, and `GET /api/state` exposes it. (A second SSE channel is not needed; the 3-route shape survives.)

## 5. What This Changes Upstream (infra v2 spec inputs)

1. **Domain core gains the Host/Tag/selector triple** — `fleet.yml` (hosts + tags) becomes the L0 source of truth; `inventory.yml` becomes generated (tag → group), which also pre-shapes the Terraform handoff (Terraform output → same `fleet.yml` schema).
2. **Fleet shape: one 3-node practice cluster, zero snowflakes** (decided in §6) — clouder = tainted CP, srv1 + srv2 = workers, all node traffic over NetBird; the mgmt plane stops being a special case. The site/cells model remains the documented fallback if the WAN cluster proves chronically flaky.
3. **Playbook surface shrinks again** — `netbird-backup.yml` and the compose-based mgmt stack fold into gitops; the infra repo's three roles cover every host identically.
4. **Console v2 scope:** host-centric fleet board, tag-filtered action targeting, ansible-runner events, per-host status lights. Same invariants, same 3 routes.

## 6. Topology Decision (2026-06-11): the Site Model

Proposal considered: one 3-node cluster — `clouder` (small box) as control plane, `srv1` + `srv2` as workers. Measured before deciding:

| Path | RTT (avg) | Verdict |
| --- | --- | --- |
| clouder ↔ srv2 | **0.5–1.7 ms** | same datacenter — real cluster semantics possible |
| clouder ↔ srv1 | ~64 ms | WAN — never stretch a cluster across this |
| srv1 ↔ srv2 | ~64 ms | WAN — ditto (this is v1's original 66 ms lesson) |

Hardware: clouder 1 vCPU / 4 GB / 50 GB · srv1 2 vCPU / 8 GB / 100 GB · srv2 2 vCPU / 8 GB / 100 GB.

**Decision (revised same day): one 3-node practice cluster, nodes meshed over NetBird.**

First pass said "half the proposal" (clouder+srv2 cluster, srv1 separate cell) on operability grounds. Then the *actual* goal surfaced: **practice the CP + multi-worker topology** ahead of a planned move to AWS (own VPS nodes side-by-side, or EKS's managed CP), so the eventual change is small and boring. That flips the objective function — latency tax and partition flapping become accepted *training costs*, not defects, and the topology should match the destination as closely as the hardware allows.

- **Topology:** `clouder` = k3s server (CP), tainted `NoSchedule` (1 vCPU / 4 GB carries CP + NetBird mgmt only); `srv1`, `srv2` = agents. 1 CP + 2 workers — the destination shape.
- **Transport:** every node's `--node-ip` is its NetBird (`wt0`, 100.x) address — **all** node↔node and pod↔pod traffic rides WireGuard, killing the plaintext-vxlan-over-WAN problem. clouder↔srv2 stay fast (NetBird peers in the same DC connect direct P2P, so the 1.7 ms pair barely notices the encryption).
- **The ghost to respect — MTU.** v1's WireGuard failures (flannel-wg crash loops, the wg0 mesh black-holing large flows) were MTU/offload pathologies. Riding flannel over `wt0` is a different, saner path: NetBird manages its own MTU (~1280) and flannel derives pod MTU from the underlying interface automatically. Verify once with a large-payload test (`dd | nc` or an iperf pod) before declaring victory — that exact test is what v1 skipped.
- **Bootstrap acyclicity (NetBird mgmt lives *in* this cluster):** WireGuard data plane survives mgmt downtime (peers keep established keys), and cold start works because clouder (CP) + the mgmt pod come up without needing the mesh; srv1/srv2 reconnect as soon as mgmt is serving. The rule that keeps this safe: **the CP node must never depend on the mesh to reach itself** — k3s API advertised on both public and wt0 IPs (`tls-san`).
- **Placement discipline = the actual practice:** stateful/chatty capabilities (postgres, redis, mq, zitadel) get nodeSelectors pinning them to `srv2` (same DC as CP); stateless app replicas float freely across both workers. Learning affinity, taints, drains, PDBs, and node upgrades on this rig transfers 1:1 to AWS.
- **What does NOT transfer — don't learn the wrong lessons:** the 64 ms cross-node hop and VPN-underlay quirks don't exist on AWS (same-VPC nodes are sub-ms). If a Service feels slow here, suspect the WAN hop before suspecting Kubernetes.
- **Revert path stays cheap:** provisioning is tag-driven, so falling back to the site model (cell A + cell B) is a fleet.yml edit + re-run, not a redesign. If the WAN cluster misbehaves chronically, that's the exit.

```yaml
hosts:
  clouder: { addr: 72.62.170.85,  tags: [cp] }       # k3s server, tainted; NetBird mgmt pinned here
  srv1:    { addr: 31.220.54.40,  tags: [worker] }   # remote worker (64 ms, via NetBird)
  srv2:    { addr: 72.62.161.127, tags: [worker] }   # local worker (1.7 ms from CP)
```

**Why this also makes the AWS move smooth (the real point):** the gitops repo never knows any of this — manifests, Flux roots, capability components are cloud-agnostic. Only the infra repo (L0/L1: how nodes exist and join) changes per provider. Moving to AWS = swap the acquisition/join layer, point Flux at the same gitops tree, done. That smoothness comes from the v2 layering, and this practice cluster exercises it for real.

(Side note from the measurement run: srv1 → clouder ICMP is 100 % filtered while clouder → srv1 works — asymmetric firewall rule, worth normalizing in the `firewall` role.)

## 7. Open Questions

Resolved 2026-06-10:

- ~~Where does the Flux git remote live?~~ **GitHub** — no circular dependency; the everything-k3s migration is unblocked.
- ~~Zot/Gitea keep-or-kill~~ — **removed**, not migrated (see §3).
- ~~NetBird data safety~~ — **backup-first, restore-proven migration order** added to §3.

Still open:

- NetBird control plane on k3s: confirm a maintained chart/manifest path exists (it does for the main components, but verify versions against the pinning discipline).
- Tag vocabulary: start with the smallest set that's real (`cell`, `canary`) and refuse speculative tags until a playbook actually branches on them (YAGNI applies to taxonomy too).
