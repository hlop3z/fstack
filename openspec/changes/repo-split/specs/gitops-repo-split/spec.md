## ADDED Requirements

### Requirement: Repo contents split by survival rule
Files MUST be assigned by the rule "would this survive the EKS move?": the gitops repo receives `gitops/**`, `bump-image.sh`, gitops CI jobs, gitops-authoring ops actions and their source secrets (ghcr/Discord/deadman); the infra repo keeps fleet.yml, Ansible, host-ops, and foundation secrets (netbird setup key). History for `gitops/**` MUST be preserved in the new repo.

#### Scenario: Self-contained gitops repo
- **WHEN** the split completes
- **THEN** the gitops repo builds standalone (kustomize roots, sops lint, pin lint in its own CI) and contains its own `.sops.yaml` and `console.actions.yml`, with no references into infra-v1 paths

#### Scenario: Secrets split by concern
- **WHEN** an operator rotates `ghcr_pull_token`
- **THEN** both the source-of-truth key and the rendered Secret live in the gitops repo; `infra/secrets/infra.sops.yaml` no longer contains gitops-feeding keys

### Requirement: Zero-downtime Flux source cutover
The cluster MUST move to the new gitops repo without workload disruption: a second GitRepository is added side-by-side, each Kustomization's sourceRef (and path) flips individually starting with the lowest-stakes one, each flip is verified Ready at the same revision content before the next, and the old source is removed only after all flips.

#### Scenario: Ordered flip with verification
- **WHEN** the `slo` Kustomization is flipped to the new source
- **THEN** it reconciles Ready with identical applied objects (no diff, no restarts) before any further Kustomization is flipped

#### Scenario: Rollback path
- **WHEN** a flipped Kustomization fails to reconcile against the new source
- **THEN** flipping its sourceRef back to the old GitRepository restores the prior state without manual object surgery

### Requirement: External writers retarget
Anything that writes to the gitops tree MUST point at the new repo after the split: the website-template release job opens its digest-bump PR against `dufeutech/gitops`, and the operator console authors gitops via the new repo as a console target.

#### Scenario: Release PR lands in the new repo
- **WHEN** a `vX.Y.Z` tag is pushed on website-template after cutover
- **THEN** the bump PR is opened on `dufeutech/gitops` and merging it deploys via Flux
