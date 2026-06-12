## Why

The fleet currently lives in two repos with mixed lifecycles: fstack (public tool) leaks fleet-specific knowledge (`secret.sh` hardcodes key names and render maps), and infra-v1 (private) mixes the disposable foundation (Ansible L0/L1 — the hand-built VPC/EKS substrate) with the durable gitops layer that must survive the EKS move unchanged. Splitting now is cheapest: every gitops component added before the split raises the Flux-cutover surface.

## What Changes

- **Phase 0 — repo-agnostic tool:** the target repo declares a `secrets:` manifest in `console.actions.yml` (SOPS file path, encrypted-suffix convention, derived-secret render map); the console gains a generic `secret` CLI subcommand (`set|get|list|rm`, with auto re-render of derived gitops Secrets); the fleet-specific `secret.sh` is **removed from the public repo** (thin wrapper moves to infra-v1).
- **Phase 1 — split gitops out:** new private repo `dufeutech/gitops` (history-preserving) receiving `gitops/**`, `bump-image.sh`, gitops CI jobs, gitops-authoring ops (`ghcr-pull-secret`, `alerts-discord`, `dns-*`), its own `console.actions.yml` + `.sops.yaml`, and the gitops-feeding secrets split out of `infra/secrets/infra.sops.yaml`. Zero-downtime Flux cutover via side-by-side GitRepository + per-Kustomization sourceRef flip. Release pipeline (website-template) retargets the new repo.
- **Phase 2 — foundation-only infra-v1:** what remains is fleet.yml + Ansible + host-ops + foundation secrets; README states the contract (*disposable by design; replaced by Terraform at EKS*).
- **BREAKING** (operator-facing): `./secret.sh` invocation moves from fstack to the target repo (`scripts/secret.sh` / `console secret`); gitops commits move to the new repo.

## Capabilities

### New Capabilities
- `console-secrets`: repo-agnostic secret management — the console reads the target repo's `secrets:` manifest and provides set/get/list/rm + derived-secret re-render, with the plaintext-suffix guard.
- `gitops-repo-split`: the standalone gitops repo — content set, secret split by concern, CI, actions surface, and the zero-downtime Flux source cutover procedure.

### Modified Capabilities
<!-- none — existing console action/run specs are unchanged; this adds a new surface -->

## Impact

- **fstack (public):** console core (+`secret` subcommand), `secret.sh` removed, compose docs; no fleet references remain.
- **infra-v1 (private):** loses `gitops/**` + gitops scripts/CI/secrets; keeps foundation; gains thin secret wrapper.
- **new `dufeutech/gitops` (private):** becomes Flux's source of truth; needs deploy key + CI + `INFRA_DEPLOY_TOKEN` re-scope in website-template.
- **Cluster:** flux-system GitRepository/Kustomization sourceRef edits (live, ordered, reversible); no workload restarts expected.
