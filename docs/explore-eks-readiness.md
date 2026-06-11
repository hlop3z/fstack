# Explore: EKS-Readiness Gap Analysis — What's Missing to Make AWS a Walk in the Park

**Date:** 2026-06-11
**Premise:** the practice cluster should exercise every platform concern you'd own on EKS, so the move is "swap the infra layer, keep everything above it." Things AWS *manages for you* are deliberately out of scope — practicing them is wasted effort.

---

## What you already have (this is a lot)

| Concern | Have | EKS-equivalent |
| --- | --- | --- |
| GitOps engine | Flux (the only L2 writer) | Flux/Argo on EKS — identical |
| Declarative cluster spec | fleet.yml + kustomize + Helm | identical |
| Secrets | SOPS + age, gitops-rendered | SOPS or External Secrets |
| Metrics | VictoriaMetrics + dashboards + Discord alerts | Prometheus/AMP + Grafana |
| Logs | VictoriaLogs + Vector | Loki/CloudWatch |
| Database | CNPG (operator-managed PG + S3 PITR) | CNPG/RDS |
| Ingress + TLS | Traefik + cert-manager (LE) | ALB/Traefik + cert-manager |
| NetworkPolicies | platform + web default-deny | Calico/Cilium netpol |
| Pinned everything | digests, vendored charts, CI lints | identical discipline |

The CRD-driven operator model (CNPG, VM Operator, cert-manager) **is** the EKS skill. You're already fluent in it.

---

## TIER 1 — the genuine "EKS minimum" gaps

These are things a real cluster has that you don't, and all transfer 1:1.

### 1. external-dns  ⭐ (highest value — fixes a pain that already bit us)
You flip Cloudflare records *by hand* (and missing the grafana record cost an hour of confusion). EKS shops never touch DNS — `external-dns` reconciles Route53/Cloudflare from Ingress annotations automatically. Add it pointed at Cloudflare; DNS becomes declarative. **This is the clearest gap and removes a whole class of human error.**

### 2. metrics-server + HPA
You have **no autoscaling at all** — not even the metrics-server HPA needs. k3s can bundle metrics-server; enable it, then put an HPA on dufeut-site (scale on CPU). Core Kubernetes, transfers verbatim, and you currently can't demo the single most basic scaling primitive.

### 3. Pod Security Standards + ResourceQuota + LimitRange
Free, built-in admission. Label namespaces `pod-security.kubernetes.io/enforce: restricted`, add a `ResourceQuota` + `LimitRange` per namespace. This is table-stakes governance every EKS platform team enforces, and it's zero new components.

### 4. Velero — whole-cluster backup/restore to S3
You back up Postgres and NetBird, but not the *cluster* (all k8s resources + PVs). Velero is the EKS DR standard; it also makes your "cattle cell" story real — restore an entire cell from S3. High value, one component.

### 5. Gateway API (evolve Traefik)
EKS is moving from Ingress to **Gateway API** (the portable successor; Traefik, Istio, and AWS all implement it). Adopting Gateway API now means your routing manifests move to EKS unchanged. Medium effort, future-proof.

---

## TIER 2 — "EKS-grade platform" (makes the move feel trivial + looks senior)

### 6. Kyverno — policy-as-code
The platform-team staple. Enforce: no `:latest`, every pod has limits + probes, no privileged containers, required labels. Your CI lints git; Kyverno enforces in-cluster (defense in depth). Very EKS, very impressive, low risk.

### 7. Flux image automation (you already have the controllers!)
`image-reflector` + `image-automation` controllers are installed and **idle**. Wire them: Flux watches your registry, auto-bumps `dufeut-site` to new tags, commits to git, deploys. Closes the GitOps loop — build → auto-deploy — exactly what mature shops run.

### 8. Flagger — progressive delivery (canary)
Your fleet model already has a `canary` channel concept. Flagger does automated canary/blue-green: shift 10%→50%→100% of traffic to a new version while watching metrics, auto-rollback on errors. Uses the VictoriaMetrics you already have. The single most "senior platform" capability.

### 9. Trivy-operator — continuous vulnerability scanning
Scans running images + cluster config for CVEs and misconfigs, surfaces them as CRDs + Grafana. The security observability board. Standard on serious EKS clusters.

### 10. Distributed tracing — Tempo + OpenTelemetry
The third observability pillar (metrics ✓, logs ✓, **traces ✗**). An OTel collector + Grafana Tempo (or VictoriaTraces when GA) gives request-level latency across services. Pairs with the ingress RED dashboards.

---

## TIER 3 — staff-level / beyond EKS-default

- **Service mesh (Linkerd)** — mTLS everywhere, golden metrics per service, traffic splitting. Lighter than Istio; realizes the old Kong→Envoy vision. Heavy for 2 nodes — do it after phase 7 adds srv1.
- **Supply chain security** — cosign-sign your images in CI, Kyverno `verify-images` rejects unsigned. SLSA-style provenance. Genuinely advanced.
- **SLOs as code** — Pyrra/Sloth define SLOs (99.9% availability) → auto-generate multi-window burn-rate alerts. What SRE teams actually page on.
- **External Secrets Operator** — the other EKS secrets pattern (Secrets Manager/Vault backend). SOPS is fine; ESO is more common on EKS if you want the practice.
- **Falco** — runtime threat detection (syscall-level). Security-team tier.

---

## Deliberately OUT of scope (AWS manages these — don't practice them)

- **HA control plane** — EKS runs 3 managed CP nodes across AZs; you never see it. Your single k3s CP is *correct* for practice — the CP is cattle (re-provision + Flux).
- **Karpenter / Cluster Autoscaler** — node provisioning is cloud-API-specific. On VPS you add nodes by hand; the transferable concept is HPA (Tier 1), not node autoscaling.
- **VPC CNI / security groups / IRSA** — AWS-specific networking + IAM. NetworkPolicies + ServiceAccounts are the portable equivalents (have them).
- **Kubecost/OpenCost** — cost visibility is moot on flat-rate VPS; ResourceQuota (Tier 1) is the transferable habit.

---

## Recommended order

1. **external-dns** (kills manual DNS, immediate) → **metrics-server + HPA** (autoscaling basics) → **PSS + quotas** (governance, free).
2. **Velero** (DR) → **Kyverno** (policy) — the platform-hardening pair.
3. **Flux image automation** + **Flagger** — the progressive-delivery loop (do around/after phase 7, when srv1 doubles capacity).
4. **Trivy** + **Tempo/OTel** — security + tracing observability.
5. Tier 3 as interest/capacity allows.

**Net:** Tiers 1–2 turn this from "a working cluster" into "a platform," and every line of it lifts to EKS unchanged — on AWS you'd delete the `infra/` layer (Ansible/k3s/NetBird) and keep `gitops/` verbatim. That's the walk in the park.
