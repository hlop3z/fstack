## Context

Two repos today: fstack (public console tool; compose mounts a target repo as `/work`) and infra-v1 (private: fleet.yml + Ansible L0/L1 + `gitops/**` Flux tree + scripts + secrets). Flux's GitRepository points at infra-v1 path `gitops/clusters/prod`. The full analysis and EKS mapping live in `infra-v1/docs/repo-split-plan.md`; the governing rule is **"would this file survive the EKS move?"** (yes → gitops, no → infra, generic machinery → fstack).

## Goals / Non-Goals

**Goals:**
- Phase 0: zero fleet knowledge in the public repo; secret management driven by a target-repo manifest; one-command rotation preserved.
- Phase 1: standalone `dufeutech/gitops` with history, self-contained CI/secrets/actions; Flux cutover with no workload disruption; release pipeline retargeted.
- Phase 2: infra-v1 reduced to the disposable foundation with an explicit contract README.

**Non-Goals:**
- Phase 3 (EKS day / Terraform repo), multi-env overlays (immediately after the split, separate change), per-repo age keys (noted option, not required), console multi-target UX beyond `CONSOLE_TARGET`.

## Decisions

- **Manifest in `console.actions.yml`, not a new file** — that file is already "the target repo's declared operational surface"; secrets are part of it. Schema: `secrets: { file, encrypted_suffixes[], derived{key: action} }`.
- **`secret` becomes a console CLI subcommand** (python, `console secret …`) rather than shipped shell — testable, shared with the GUI later; a 5-line wrapper may live in each target repo for ergonomics.
- **Derived-secret render = run the mapped `ops` action** (existing `scripts/ops.sh <action>` convention in the target repo) — the console stays ignorant of what rendering means.
- **History via `git subtree split`** on `gitops/` (no extra tooling deps; filter-repo as fallback).
- **Secrets split by concern**: source-of-truth keys live beside the artifacts they feed. gitops repo gets its own `secrets/ops.sops.yaml` (ghcr/Discord/deadman) + `.sops.yaml` (same age recipient initially — key rotation is an orthogonal follow-up).
- **Flux cutover side-by-side**: new GitRepository `gitops` (own deploy key in `~/.infra/flux/`), flip Kustomizations one at a time in stakes order `slo → scrapes → policies → apps → platform → infra*` (*infra Kustomization stays only if any of its paths move), verify Ready + zero-diff each step, delete old source last. Paths change `gitops/...` → repo-root-relative.
- **fstack default `CONSOLE_TARGET` stays `../infra-v1`** as a documented example; all other fleet references removed.

## Risks / Trade-offs

- **Flux flip mid-state** (one Kustomization on new source, rest on old): acceptable — sources contain identical content during cutover; freeze gitops merges during the window.
- **Push access for the release PR**: `INFRA_DEPLOY_TOKEN` must be re-scoped to the new repo before the next release tag, else release PRs fail (fails loud, not silent).
- **Operator muscle memory / docs drift**: old repo paths archived with pointer README; operations.md updated in the same change.
- **subtree split rewrites no history in the source repo** but the new repo's commits get new SHAs — links in old commit messages won't resolve; accepted.
- **Two consoles targets** (infra vs gitops) adds a mental step; mitigated by each repo's `console.actions.yml` listing only its own actions, so the wrong target fails obviously.
