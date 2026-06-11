# Design: infra-v2

## Context

The architectural decisions are already made and documented — this design consolidates them and settles only what implementation needs. Inputs: `docs/ultra-think-infra-v2.md` (layered L0–L2 model, Approach A "Two Repos, Zero Engines"), `docs/explore-fleet-model-tags.md` (host+tags model; 3-node practice cluster over NetBird, decided §6; everything-k3s with NetBird in-cluster; Gitea/Zot removed; NetBird backup proven by production restore).

Current reality (2026-06-11):
- **clouder**: fresh Debian 13, hardened, Docker CE, NetBird control plane running as interim compose (`interim/netbird-clouder/`) with restored state; backup timer live. 1 vCPU / 4 GB.
- **srv1 + srv2**: v1's stretched k3s cluster carrying production (dufeut-site, CNPG Postgres, Garage, RabbitMQ, Redis, Zitadel, monitoring), Flux-managed from `ansible-01/gitops/` since 2026-06-09. NetBird clients Connected. 2 vCPU / 8 GB each.
- Latency: clouder↔srv2 1.7 ms; srv1 ↔ both ~64 ms (WAN). All node traffic will ride NetBird.
- Operator tooling: the `console/` spike (this repo) runs all playbooks through one Docker image.

## Goals / Non-Goals

**Goals:**
- `fleet.yml` + generated inventory replacing v1's group sprawl.
- `infra/` roles provisioning any Debian host identically; `gitops/` tree Flux-consumed from this repo's subpath.
- The 3-node practice cluster live and MTU-verified; NetBird in-cluster; production migrated with restore-first gates; ansible-01 archived.

**Non-Goals:**
- Console v2 (tag-selected actions, ansible-runner) — separate change after this lands.
- Terraform/acquisition layer; standalone infra/gitops repos (extraction deferred); Taskfile removal; HA control plane; the site-model fallback (documented escape hatch, built only if the WAN cluster proves chronically flaky).

## Decisions

### D1: Standalone private config repo (REVISED 2026-06-11, user decision during apply)
The original monorepo-subpath plan was reversed mid-apply: fstack is **public** and stays a **standalone operator tool** (the console image, downloadable); all fleet config lives in the **private `dufeutech/infra-v1`** repo (`fleet.yml`, `infra/`, `gitops/`, `scripts/`, CI). Flux pulls infra-v1 over SSH with a read-only deploy key (`~/.infra/flux/`, public half registered on GitHub). The console became target-agnostic: the target repo declares its own actions in `console.actions.yml`, which the console loads at startup — the image carries only generic built-ins. This restores the v2 doc's two-repo structural SoC *and* makes the console a real product.

### D2: Repo layout

```
fstack/
├── fleet.yml                      # L0 source of truth (hosts + tags)
├── infra/
│   ├── roles/{base,firewall,netbird_client,k3s_cp,k3s_worker}/
│   ├── playbooks/{cluster.yml,update.yml,ssh-rotate.yml}/
│   └── inventory.yml              # GENERATED from fleet.yml — never hand-edited
├── gitops/
│   ├── clusters/prod/             # Flux root: GitRepository + Kustomizations + SOPS config
│   ├── platform/components/{postgres,s3,redis,mq,oidc,monitoring,netbird}/
│   └── apps/dufeut-site/
├── scripts/gen_inventory.py       # stdlib only, fleet.yml -> inventory.yml
└── console/                       # existing spike; its actions registry gains the v2 playbooks
```

### D3: Cluster build on the NetBird underlay
k3s server on clouder: `--node-ip <wt0>`, `--node-taint node-role.kubernetes.io/control-plane:NoSchedule`, `--tls-san <public-ip>,<wt0-ip>,<api-domain?>`, pinned version, flannel default (vxlan) over wt0. Workers join via the CP's wt0 address with their own wt0 node-ips. clouder first needs the `netbird_client` role (it currently hosts mgmt but isn't a mesh peer). MTU: rely on flannel's auto-derivation from wt0 (~1280 → pod MTU ~1230), then **gate on an iperf3 large-payload pod-to-pod test across the srv1 link** before promoting the cluster. If it black-holes: clamp flannel MTU explicitly; if still broken, the site-model fallback decision point triggers.

### D4: Migration choreography (the order everything else serves)
1. Build `infra/` + `fleet.yml` + generator; provision clouder as CP (cluster of one, tainted). MTU gate needs a worker — runs at step 3.
2. Author `gitops/` by reorganizing v1's *already-Flux-consumed* rendered tree (`ansible-01/gitops/`) into components — reorganization, not rewriting; keep v1's pins and vendored charts.
3. **Drain srv2 from v1** (v1 keeps running CP+everything on srv1 — it survived as effectively single-node before), rebuild srv2, join as worker. Run the MTU gate (clouder↔srv2 and later srv1 link re-test). Flux deploys platform components to the new cluster.
4. Restore-first: CNPG restores prod DB from S3 → verify; Garage data sync from v1 → verify object counts; Zitadel comes up against restored DB → login verify; deploy dufeut-site → smoke test on a staging hostname.
5. NetBird in-cluster (pinned images replacing `:latest`), state carried from the interim compose volume; peers verified Connected; interim compose stopped (kept on disk until step 7); backup CronJob verified.
6. **DNS flip** (Cloudflare) to the new cluster's ingress after all gates; verification window (~days) with v1-on-srv1 as rollback anchor.
7. Drain/rebuild srv1, join as second worker; rebalance stateless replicas; delete interim compose dir from clouder; archive ansible-01 read-only.

### D5: What carries over verbatim from v1
Vendored charts and version pins; SOPS+age keys and encrypted blobs (re-encrypted into `gitops/` layout); CNPG backup configuration; Traefik as ingress (k3s default — Kong/Zitadel ingress remains the deleted-experiment question, explicitly NOT decided here); Cloudflare origin certs pattern. The `update.yml`/`ssh-rotate.yml` playbooks port nearly as-is into roles.

### D6: Console integration is registry-only
The spike console gains v2 actions (`fleet:gen-inventory`, `cluster:provision`, `host:update`) as registry entries pointing at `infra/` playbooks — no console code changes (that's console v2's job). `CONSOLE_TARGET` flips from ansible-01 to fstack.

## Risks / Trade-offs

- **[MTU/offload black-hole repeats v1's WireGuard failure]** → mandatory iperf gate before any workload moves (spec-level); explicit flannel MTU clamp as first remedy; documented site-model fallback as the exit. The failure mode is *detected in step 3, before production is at risk*.
- **[v1 degraded while srv2 is drained (steps 3–6: single node, reduced replicas)]** → accept consciously: dufeut-site is the only app; postgres replica count drops to 1 on v1 during the window; CNPG S3 backups continue throughout. Keep the window short (days, not weeks).
- **[Garage data sync has no Barman-equivalent]** → use `rclone`/garage replication from v1's buckets to the new Garage before cutover; verify object counts + spot checksums; re-sync delta just before DNS flip.
- **[1 vCPU CP under-provisioned]** → taint keeps it CP+NetBird-only; monitor; the remedy (resize VPS or move CP) doesn't change the architecture.
- **[Monorepo subpath blurs the L0/L2 boundary]** → CI enforces: `infra/` may not contain k8s manifests, `gitops/` may not contain Ansible; plus the existing kustomize/SOPS/pin lints.
- **[Cloudflare DNS flip behind their proxy may mask cutover issues]** → lower TTL ahead of time; test against the new ingress via hosts-file override before flipping.

## Migration Plan

D4 *is* the migration plan; rollback points: before step 6, DNS never moved (v1 authoritative); after step 6 but before step 7, flip DNS back to v1-on-srv1 (data written during the window reconciled via CNPG PITR or accepted-loss decision made at gate time). After step 7 there is no v1; recovery = the new cluster's own backup/restore paths (all verified by then).

## Open Questions

- API endpoint domain for the kubeconfig (`tls-san`): bare public IP vs `k8s.dufeut.com` record — decide at implementation (cosmetic).
- Garage sync mechanics (rclone vs garage-native replication) — decide when measuring bucket size.
- Whether the verification window keeps v1 read-only (clean) or accepts write-reconciliation (complex) — decide at gate time based on dufeut-site's write traffic.
