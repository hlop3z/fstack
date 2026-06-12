## 1. Phase 0 — repo-agnostic tool (fstack + infra-v1)

- [ ] 1.1 Add `secrets:` manifest to infra-v1 `console.actions.yml` (file, encrypted_suffixes, derived map for ghcr/discord/deadman)
- [ ] 1.2 Implement `console secret set|get|list|rm` (manifest-driven; hidden prompt; suffix guard; post-write encryption check; derived re-render via the mapped ops action; clear error when manifest missing)
- [ ] 1.3 Tests for the secret subcommand (manifest parsing, suffix guard, derived-map dispatch; sops mocked)
- [ ] 1.4 Remove `secret.sh` from fstack; add thin `scripts/secret.sh` wrapper in infra-v1 (locates sibling fstack compose; delegates to `console secret`)
- [ ] 1.5 Sweep fstack for remaining fleet references (key names, dufeut hosts) outside docs/examples; update README + operations.md usage
- [ ] 1.6 Verify end-to-end: `secret list` + a no-op `secret set` of an existing key re-renders its derived secret, file stays encrypted; commit both repos

## 2. Phase 1 — create and fill the gitops repo

- [ ] 2.1 Create private `dufeutech/gitops`; `git subtree split` infra-v1 `gitops/` with history; push as `main`
- [ ] 2.2 Make it self-contained: move `bump-image.sh`; add `.sops.yaml`, gitops-only CI (kustomize roots, sops lint, pin lint), `console.actions.yml` (image:ghcr-pull-secret, alerts:set-discord, dns:set/rm) + the ops render script; paths become repo-root-relative
- [ ] 2.3 Split secrets by concern: new `secrets/ops.sops.yaml` in gitops (ghcr_pull_token, alertmanager_discord_webhook, deadman_webhook); remove those keys from infra-v1 `infra/secrets/infra.sops.yaml`; update both `secrets:` manifests
- [ ] 2.4 CI green on the new repo before any cluster change

## 3. Phase 1 — Flux cutover (zero-downtime)

- [ ] 3.1 New deploy key (`~/.infra/flux/`) + read access on dufeutech/gitops; create side-by-side GitRepository `gitops` in flux-system (committed via the OLD repo first, then mirrored in the new)
- [ ] 3.2 Flip `slo` Kustomization sourceRef+path to the new source; verify Ready, zero object diff, no restarts
- [ ] 3.3 Flip remaining Kustomizations in stakes order (scrapes → policies → apps → platform); verify each
- [ ] 3.4 Point the flux-system root at the new repo; remove the old GitRepository; confirm full reconcile at new revisions
- [ ] 3.5 Freeze window discipline: no gitops merges between 3.2 and 3.4 (note in PRs/docs)

## 4. Phase 1 — retarget external writers

- [ ] 4.1 website-template release job: clone/PR target → dufeutech/gitops; `INFRA_DEPLOY_TOKEN` re-scoped (operator step, documented); bump-image path updated
- [ ] 4.2 Console: document/verify `CONSOLE_TARGET=../gitops` for gitops-authoring actions; infra-v1 actions file drops the moved actions

## 5. Phase 2 — foundation-only infra-v1 + docs

- [ ] 5.1 Remove `gitops/**` + moved scripts/CI jobs from infra-v1; CI reduces to inventory/boundary/ansible checks
- [ ] 5.2 READMEs: gitops repo (what it is, survives EKS); infra-v1 contract (*disposable foundation — replaced by Terraform at EKS*); operations.md repo map + updated runbooks
- [ ] 5.3 Update eks-readiness scorecard (#5 note: multi-env lands in the gitops repo next) and repo-split-plan status
- [ ] 5.4 Final verification sweep: drill cronjobs, Flagger, probes, release dry-run all healthy against the new layout
