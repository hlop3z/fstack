# Proposal: infra-v2

## Why

`ansible-01` (v1) is a mixed-concern monolith — 17 role-less playbooks, a retired-but-present Go platform manager, a custom JS renderer, and two engines owning Day-2 — that is hard to operate and maintain (full analysis: `docs/ultra-think-infra-v2.md`). The replacement design is settled and partially proven: Flux is already the production Day-2 engine, the fleet/tags model and 3-node practice-cluster topology are decided (`docs/explore-fleet-model-tags.md`), clouder is freshly rebuilt (Debian 13, hardened, NetBird control plane restored from a verified backup), and the operator console spike works against the real fleet. This change builds v2 and migrates production onto it.

## What Changes

- **New `fleet.yml`** — the single hand-authored L0 source of truth: hosts + tags (`cp`, `worker`); Ansible inventory becomes *generated* (one group per tag), replacing v1's six-groups-for-two-servers mess.
- **New `infra/` top-level dir** (L0/L1): Ansible roles `base`, `firewall`, `netbird_client`, `k3s_cp`, `k3s_worker`; playbooks `cluster.yml` (provision/join by tag), `update.yml`, `ssh-rotate.yml`. Distills v1's 17 playbooks; the firewall role kills the UFW ×4 duplication.
- **New 3-node practice cluster**: clouder = k3s server, tainted `NoSchedule` (CP + NetBird mgmt only); srv1 + srv2 = agents. All node↔node traffic over NetBird `wt0` (encrypted), with an explicit large-payload MTU verification gate (v1's WireGuard failures were MTU pathologies).
- **New `gitops/` top-level dir** (L2): Flux root `clusters/prod/`, `platform/components/` (cnpg-postgres, garage-s3, redis, rabbitmq, zitadel, monitoring, netbird), `apps/dufeut-site/`; SOPS+age decryption in-cluster. Flux watches the `gitops/` subpath of this repo (extraction to a standalone repo is deferred to a later change).
- **NetBird control plane moves in-cluster** — from the interim compose (`interim/netbird-clouder/`) to a Flux-managed workload pinned to clouder, state carried over; the in-cluster backup CronJob replaces `netbird-backup.yml`.
- **Production migration, backup-gated**: dufeut-site + CNPG Postgres + Garage + RabbitMQ + Redis + Zitadel + monitoring move from the v1 stretched cluster to the new cluster — srv2 rebuilt and joined first (workloads restored there), then srv1 drained, rebuilt, joined.
- **BREAKING / terminal**: the v1 stretched cluster is torn down; `ansible-01` is archived read-only at the end (Go platform manager, jkub, SQLite ledger, WireGuard-mesh playbooks all die with it).
- **Out of scope**: console v2 (separate change), Terraform/acquisition layer, Taskfile removal, multi-cell/site fallback (documented escape hatch only).

## Capabilities

### New Capabilities

- `fleet-model`: the `fleet.yml` schema (hosts, addresses, tags), tag vocabulary rules, and generated-inventory contract — the L0 source of truth.
- `host-provisioning`: Debian base hardening, firewall policy, and NetBird client join — identical on every host, role-based, no copy-paste.
- `cluster-provisioning`: k3s server/agent install by tag over the NetBird underlay — taints, `tls-san`, node-ip discipline, MTU verification gate, and Flux bootstrap.
- `gitops-delivery`: the gitops tree layout, Flux Kustomization wiring, SOPS+age secret decryption, and the "Flux is the only L2 writer" rule.
- `platform-capabilities`: the per-capability kustomize components (postgres, s3, redis, mq, oidc, monitoring, netbird) with v1's pinning discipline and placement rules (stateful pinned near CP's site, stateless floats).
- `production-migration`: the backup-gated cutover sequence, per-service data restore verification, DNS flip, and v1 decommission criteria.

### Modified Capabilities

<!-- none in openspec/specs yet; infra-console-spike's capabilities are untouched by this change -->

## Impact

- **New code/config:** `fleet.yml`, `infra/` (~3–5 roles + 3 playbooks), `gitops/` (Flux + kustomize YAML, vendored chart references), a small inventory generator (stdlib Python, `scripts/`).
- **Deleted at the end:** v1's operational surface — ansible-01 archived; its 17 playbooks, Go manager (8 pkgs), jkub, SQLite ledger, and the interim NetBird compose all stop being live.
- **Production risk:** dufeut-site and its data move clusters. Every stateful service migrates restore-first (CNPG from S3 backups, Garage data sync, Zitadel via its CNPG db, NetBird state already proven); each has a verification gate before its v1 source is destroyed; rollback is possible until srv1 (the last v1 node) is rebuilt.
- **Dependencies:** no new tools — Ansible, k3s, Flux, SOPS+age, NetBird, kustomize; all already in use. The console (spike) is the operator surface for playbook runs.
- **External systems:** Cloudflare DNS records flip to the new cluster's ingress at cutover; Hostinger edge firewall rules reviewed per host; GitHub (this repo) becomes the Flux source.
