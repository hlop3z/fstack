# Tasks: infra-v2

> NOTE (2026-06-11, design D1 revised): all config artifacts live in the PRIVATE
> repo `dufeutech/infra-v1` (pushed, commit e524195), not fstack. fstack is the
> public console tool; the target repo declares actions via `console.actions.yml`.

## 1. Fleet model + scaffolding

- [x] 1.1 `fleet.yml` (clouder `[cp]`, srv1/srv2 `[worker]`, per-host `labels` for k3s node labels)
- [x] 1.2 `scripts/gen_inventory.py` (PyYAML): fleet.yml → `infra/inventory.yml`; `--check` mode for CI
- [x] 1.3 Scaffolded `infra/` + `gitops/` (in infra-v1)
- [x] 1.4 CI (infra-v1): kustomize build all roots; SOPS lint; pin lint; boundary lint; inventory freshness; ansible syntax check
- [x] 1.5 Console: target-repo action loading (`console.actions.yml`) replaces hardcoding; `CONSOLE_TARGET` default `../infra-v1`; infra-v1 declares fleet:gen-inventory / host:update / cluster:provision / ssh:rotate — all 6 verified loading

## 2. Infra roles (L0)

- [x] 2.1 `base` role (Debian 13, from v1 setup.yml)
- [x] 2.2 `firewall` role: one home for UFW; provider-edge mode (clouder); symmetric fleet ICMP; wt0 allowed wholesale
- [x] 2.3 `netbird_client` role: pinned 0.71.4 deb + setup-key join via community.sops; idempotent (wt0 check)
- [x] 2.4 `update.yml` (serial, reboot report) + `ssh-rotate.yml` ported
- [x] 2.5 clouder hardened + mesh-joined (Management/Signal Connected); setup key SOPS-encrypted in `infra/secrets/infra.sops.yaml`, raw operator copy at `~/.infra/netbird/setup-key`

## 3. Cluster provisioning (L1)

- [x] 3.1 `k3s_cp` role: pinned v1.35.5+k3s1; node-ip/advertise/flannel-iface on wt0; CP taint; tls-san public+wt0; kubeconfig → ~/.infra/kube/prod.yaml
- [x] 3.2 `k3s_worker` role: join over CP wt0; node labels from fleet.yml; ServiceLB pinned to workers (`enablelb` label) so the interim compose's 80/443 on clouder don't conflict
- [x] 3.3 `cluster.yml`: tag-selected plays; asserts wt0 before k3s
- [x] 3.4 clouder IS the CP: k3s v1.35.5+k3s1 Ready, node-ip on wt0, CP taint verified, kubeconfig at `~/.infra/kube/prod.yaml` (public-IP server)
- [x] 3.5 Flux LIVE: v2.8.8 via k3s manifests dir (4 core controllers Running — patched with CP tolerations, a cluster-of-one lesson; image-automation/reflector/notification left Pending, unused); GitRepository Ready at `main@e524195` over the deploy key (after fixing a Windows ssh-keygen quoting bug that passphrase-locked it); root Kustomization reconciling, infra/platform/apps children spawned, first HelmRelease pulling. Platform/apps will sit not-ready until srv2 joins (phase 5) — documented expected state

## 4. GitOps tree (L2 authoring)

- [x] 4.1 v1 tree reorganized into `platform/{base,operators,components/{postgres,redis,mq,s3,oidc,monitoring}}` keeping pins + vendored charts (chart paths updated). Deliberate deltas, documented in-file: db-main instances 2→1 (no cross-WAN replica; S3 PITR is the net; WAL path moved to `db-main-v2` so v1's chain stays untouched), mq replicas 2→1, garage 2→1 (grow layout when srv1 joins), monitoring → srv2 (CP is tainted + 1 vCPU)
- [x] 4.2 `apps/dufeut-site/` + 9 secrets fetched from the LIVE v1 cluster and SOPS-encrypted into the tree (origin-tls ×2, db-backup-s3, cache-auth, zitadel-env, zitadel-masterkey, grafana-admin, dufeut-smtp, netbird-backup-s3); plaintext dumps deleted
- [x] 4.3 Placement: stateful nodeSelectors → srv2 labels; CP tolerations only on netbird + its backup CronJob
- [x] 4.4 `netbird` component: digest-pinned to the EXACT images proven by the restore; CP-pinned; IngressRoute mirroring the compose routing (h2c gRPC split); cert-manager component (LE; vpn host isn't CF-proxied); backup CronJob (same archive shape, `netbird-state/k8s/` prefix). Opted-in at phase 6, builds standalone now
- [x] 4.5 Root wiring complete; all 12 kustomize roots build clean (verified in-container); CI live on infra-v1

## 5. srv2 cutover (production migration, part 1) — ✅ COMPLETE 2026-06-11

- [x] 5.1 Pre-flight: primary confirmed on srv1; fresh backup `pre-v2-migration` completed; garage inventory (1 bucket `uploads`); placement mapped
- [x] 5.2 srv2 drained/deleted from v1 (with in-command CP guard); dufeut.com stayed 200 throughout; v1 single-node on srv1 = rollback anchor
- [x] 5.3 srv2 joined new cluster (fixed k3s_worker delegation bug for -l limits); labels + enablelb applied
- [x] 5.4 MTU gate PASSED: iperf3 pod-to-pod 428 Mbit/s, 0 loss, byte counts match (srv1 path re-tests at 7.2)
- [x] 5.5 Platform deployed via Flux. Fixes en route, all in git: barman-cloud plugin v0.12.0 + cert-manager (the ObjectStore CRD v1 installed by script), HelmRelease install+upgrade remediation, zitadel 20m timeout, monitoring chart-default nodeSelector nulled
- [x] 5.6 Restore-first VERIFIED: db-main recovered from v1's object store (zitadel db + 5 users — exact match vs v1 live primary); garage layout initialized. **Phase-6 checklist learned:** CNPG post-recovery resets the superuser password (sync zitadel-env) but NOT restored app roles (ALTER ROLE main to the db-main-app secret)
- [x] 5.7 dufeut-site 2/2 Running on srv2 (imported image); **smoke via srv2 ingress: dufeut.com=200, auth.dufeut.com=200**; zitadel init Completed, server+login Running

## 6. NetBird in-cluster + DNS cutover

- [x] 6.1 NetBird in-cluster on srv2 (LB-owning worker, not CP): config/dashboard as SOPS secrets, state transplanted into PVC, LE cert issued, interim compose stopped (on disk for rollback), vpn.dufeut.com flipped to srv2 (TTL 60), ALL peers reconnected. Fixes: NAT-hairpin hosts entry on the LB worker (folded into netbird_client role)
- [x] 6.2 In-cluster backup CronJob round-trip VERIFIED (`netbird-identity-k8s-…tar.gz`: store/{store,idp,events}.db + config.yaml). Backup uses file-copy (rclone image has no sqlite). Host-level timer on clouder still present — remove at phase 7 decommission
- [x] 6.3 **CUTOVER COMPLETE** — dufeut.com + auth.dufeut.com + vpn.dufeut.com now resolve to srv2 ONLY; all serve 200 through Cloudflare via real DNS. Discoveries: (a) hostnames had DUAL A records (v1's 2-node HA: srv1+srv2) — so ~50% of prod silently hit the new cluster since srv2 joined in phase 5; completed by DELETING the srv1/v1 records. (b) No destructive db re-recovery needed — identities verified identical (5 users/1 org/2 projects on both), dufeut is DB-less/static, Garage uploads bucket empty (0 objects). Rollback = re-add the 31.220.54.40 A records (v1 intact on srv1)
- [x] 6.4-pre: CoreDNS hardened to 2 replicas one-per-node + PDB (fixes the cross-node DNS SPOF that the flannel-flap exposed); VERIFIED by killing one node's CoreDNS — the other node still resolved. Encoded in k3s_cp role
- [ ] 6.4 Verification window (days): monitor app/DB/mesh/backups; v1-on-srv1 = rollback anchor until phase 7

### Phase-6 firefight log (all fixed, in git)
- cert-manager webhook stranded on srv2 → cross-node API→webhook timeouts wedged the whole platform Kustomization → pinned cert-manager to the CP (same node as API server). Schema rejected YAML anchors; inlined.
- **Flannel-VXLAN-over-wt0 desync**: netbird restarts flapped wt0; flannel routes+FDB on clouder/srv2 went stale → srv2↔clouder pod traffic 100%-dropped → DNS dead (CoreDNS is clouder-only) → S3 name resolution failed → backups + CNPG WAL archiving failed. Fixed by `systemctl restart k3s`/`k3s-agent` to rebuild flannel over current wt0. Documented in firewall role with a resilience TODO (multi-node CoreDNS).

## 7. srv1 + decommission (terminal) — ✅ COMPLETE 2026-06-11

- [x] 7.1 Production gate passed (all 4 hostnames 200 on new cluster, data verified); v1 k3s decommissioned/wiped from srv1; srv1 provisioned + joined as 2nd worker (node-storage) over wt0. Capacity doubled: srv2 98%→14% CPU
- [x] 7.2 MTU gate GREEN across the srv1 WAN link: pod-to-pod iperf 188 Mbit/s, no black-hole over 64 ms WireGuard; controllers de-pinned from node-monitoring and spread across both workers
- [x] 7.3 Interim NetBird compose dir + host backup timer removed from clouder (in-cluster CronJob verified taking over). Remaining: prune the dead pre-wipe clouder peer + offline laptop in the NetBird dashboard (operator, cosmetic)
- [x] 7.4 ansible-01 archived read-only (see closeout); docs updated
- [x] 7.5 Invariants hold: one engine per layer (Flux only L2 writer), generated inventory, no snowflakes (3 identical-shape hosts), all gitops-managed. Console-v2 deltas (tag-selected actions, ansible-runner per-host events) tracked in explore-nicegui doc

### Beyond migration: EKS-readiness platform (Tiers 1–2, this session)
external-dns (declarative DNS) · HPA + metrics-server · Pod Security Standards + ResourceQuota/LimitRange · Velero (cluster DR to S3) · Kyverno (3 audit policies) · Trivy (CVE scanning, 49+ reports) · Tempo + OTel (tracing pipeline) · Flagger (canary controller). All gitops-managed, all transfer to EKS. Deferred: Gateway API migration, Flux image automation (needs write deploy key), per-app Flagger Canary, Linkerd/cosign/SLOs (Tier 3) — see docs/explore-eks-readiness.md.
