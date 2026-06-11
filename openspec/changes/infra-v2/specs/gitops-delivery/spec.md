# gitops-delivery — Spec Delta

## ADDED Requirements

### Requirement: Flux is the only L2 writer
All Kubernetes state SHALL be declared in `gitops/` and applied exclusively by Flux. No human `kubectl apply`, no Ansible-applied manifests, no second engine. Deploys are `git push`.

#### Scenario: Drift self-heals
- **WHEN** a resource managed by Flux is mutated or deleted by hand
- **THEN** the next reconciliation restores it to the declared state

### Requirement: Tree layout separates cluster roots, platform, and apps
The gitops tree SHALL be: `clusters/prod/` (the Flux Kustomization root), `platform/components/<capability>/` (opt-in kustomize components), and `apps/<app>/` (base + per-cluster overlay). A cluster opts into a capability by referencing its component from the cluster root — composition is structural, validated by `kustomize build` in CI.

#### Scenario: Capability opt-in is one reference
- **WHEN** a cluster should gain a capability (e.g. redis)
- **THEN** the change is one component reference in `clusters/prod/`, and `kustomize build` proves it resolves

#### Scenario: CI gate
- **WHEN** a PR touches `gitops/`
- **THEN** CI runs `kustomize build` over every cluster root and fails on dangling references

### Requirement: Secrets are SOPS-encrypted in git and decrypted only in-cluster
Every Secret in `gitops/` SHALL be a SOPS+age-encrypted file; kustomize-controller decrypts using the age key Secret created at bootstrap. CI SHALL lint that no unencrypted Secret manifest exists in the tree.

#### Scenario: Plaintext secret blocked
- **WHEN** a PR adds a Kubernetes Secret that is not SOPS-encrypted
- **THEN** the CI secrets lint fails the PR

### Requirement: Version pinning discipline carries over from v1
Every image SHALL be tag- or digest-pinned and every chart reference version-pinned (v1's existing discipline). `:latest` SHALL fail CI lint. The interim NetBird compose's `:latest` images are replaced with pins when NetBird moves in-cluster.

#### Scenario: latest rejected
- **WHEN** a manifest references an image without a pinned tag/digest
- **THEN** CI fails with the offending reference named
