# Tasks: infra-v2

## 1. Fleet model + scaffolding

- [ ] 1.1 Write `fleet.yml` (clouder `[cp]`, srv1 `[worker]`, srv2 `[worker]`, addresses, ssh key ref)
- [ ] 1.2 `scripts/gen_inventory.py` (stdlib): fleet.yml → `infra/inventory.yml` (group per tag + `all`, ansible_host wiring); idempotent; refuses to run if fleet.yml invalid
- [ ] 1.3 Scaffold `infra/` (roles + playbooks dirs, ansible.cfg pointing at generated inventory) and `gitops/` (clusters/prod, platform/components, apps)
- [ ] 1.4 CI checks (GitHub Actions): `kustomize build` all cluster roots; SOPS lint (no plaintext Secrets); pin lint (no `:latest`); boundary lint (`infra/` has no k8s manifests, `gitops/` no Ansible); inventory freshness (`gen_inventory.py --check`)
- [ ] 1.5 Console registry: add `fleet:gen-inventory`, `cluster:provision`, `host:update` actions; flip `CONSOLE_TARGET` default to fstack

## 2. Infra roles (L0)

- [ ] 2.1 `base` role: distill v1 `setup.yml` (apt, SSH hardening, fail2ban, sysctl, swap, unattended-upgrades, timezone) for Debian 13
- [ ] 2.2 `firewall` role: single home for UFW logic; provider-edge mode (clouder); symmetric fleet ICMP; k3s/NetBird port matrix from one vars table
- [ ] 2.3 `netbird_client` role: pinned client install + setup-key join (SOPS secret); idempotent re-run; verify wt0 up
- [ ] 2.4 `update.yml` + `ssh-rotate.yml` ported from v1 playbooks onto the roles/inventory
- [ ] 2.5 Run `base`+`firewall`+`netbird_client` on clouder (it lacks a mesh client today); verify clouder appears as a NetBird peer

## 3. Cluster provisioning (L1)

- [ ] 3.1 `k3s_cp` role: pinned k3s server; `--node-ip` = wt0; CP taint; `tls-san` public+wt0; kubeconfig fetched to operator
- [ ] 3.2 `k3s_worker` role: agent join via CP wt0 address, node-ip = wt0
- [ ] 3.3 `cluster.yml` playbook: tag-selected (cp → server, worker → join); refuses hosts missing wt0
- [ ] 3.4 Provision clouder as CP (cluster of one); verify API reachable on public + wt0; taint effective
- [ ] 3.5 Flux bootstrap in `k3s_cp` role: install Flux, GitRepository → this repo `gitops/clusters/prod/`, age-key Secret; verify reconciliation of an empty root

## 4. GitOps tree (L2 authoring — no cluster needed)

- [ ] 4.1 Reorganize v1's rendered `ansible-01/gitops/` tree into `gitops/platform/components/{postgres,s3,redis,mq,oidc,monitoring}` keeping pins + vendored chart references
- [ ] 4.2 `gitops/apps/dufeut-site/` base + prod overlay; SOPS re-encrypt its secrets into the new layout
- [ ] 4.3 Placement rules: nodeSelectors pinning stateful components to srv2; CP tolerations only where intended
- [ ] 4.4 `netbird` component: pinned images (replacing interim `:latest`), CP-pinned with toleration, same public endpoints (vpn.dufeut.com via ingress, STUN 3478 hostPort), state PVC, backup CronJob writing v1's archive shape to the same S3 prefix
- [ ] 4.5 `clusters/prod/` root wiring all components; CI green on the whole tree

## 5. srv2 cutover (production migration, part 1)

- [ ] 5.1 Pre-flight: fresh CNPG backup verified in S3; Garage bucket inventory (sizes/counts) captured; v1 confirmed healthy on srv1 alone (drain rehearsal)
- [ ] 5.2 Drain srv2 from v1 (cordon, drain, remove from v1 cluster); v1 continues single-node on srv1
- [ ] 5.3 Rebuild srv2 (base/firewall/netbird roles), join new cluster as worker
- [ ] 5.4 **MTU gate**: iperf3 pod-to-pod clouder↔srv2 and srv2↔srv1's future path (large payload, both directions); clamp flannel MTU if black-holing; do not proceed until clean
- [ ] 5.5 Flux deploys platform components; all healthy on srv2
- [ ] 5.6 Restore-first verification: CNPG restore from S3 → app-level query check; Garage sync (rclone) → object count + spot checksums; Zitadel up against restored DB → login check
- [ ] 5.7 Deploy dufeut-site on new cluster; smoke test via hosts-override hostname (TLS serving)

## 6. NetBird in-cluster + DNS cutover

- [ ] 6.1 Carry NetBird state from interim compose volume into the component's PVC; bring up in-cluster NetBird; verify all peers reconnect without re-enrollment
- [ ] 6.2 Stop interim compose (leave on disk); first in-cluster backup CronJob run round-trip verified; remove host-level backup timer
- [ ] 6.3 Lower Cloudflare TTLs; final Garage delta sync; **DNS flip** to new cluster ingress after all gates green
- [ ] 6.4 Verification window (days): monitor app, DB, mesh, backups; v1-on-srv1 untouched as rollback anchor

## 7. srv1 + decommission (terminal)

- [ ] 7.1 After the window: capture final v1 state notes; drain srv1, rebuild (roles), join as second worker
- [ ] 7.2 Re-run MTU gate across the live WAN link (clouder/srv2 ↔ srv1); rebalance stateless replicas across workers
- [ ] 7.3 Delete interim compose dir from clouder; prune dead peers (old clouder, stale entries) in NetBird dashboard
- [ ] 7.4 Archive `ansible-01` read-only (final commit links this change); update fstack docs (ultra-think + fleet doc) with as-built notes
- [ ] 7.5 Post-migration review: confirm invariants hold (one engine per layer, generated inventory, no snowflakes); list deltas for console-v2 change
