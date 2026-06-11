# Explore: Grafana as the Single Pane — Rancher/EKS-Grade Visibility, Big-Shop Practice

**Date:** 2026-06-11 · **Status:** explorable idea → next openspec change after phase 5–7
**Goal:** everything Rancher/EKS would show (inventory, images, helm releases, counters) plus what large operations teams *actually* watch — built on the stack already deployed (Prometheus, Grafana, Loki+promtail, kube-state-metrics, node-exporter, Alertmanager).

## The principle big shops follow

Two vocabularies cover 90% of real dashboards:
- **USE** for resources (Utilization, Saturation, Errors) — nodes, disks, network.
- **RED** for services (Rate, Errors, Duration) — everything behind the ingress.
Plus one meta-rule: **a dashboard you don't alert from is a poster.** Every board below ships with its alert rules.

## The dashboard set (the curriculum)

| Board | What it shows | Metric sources (already emitting or one toggle away) | What it teaches |
|---|---|---|---|
| **1. Cluster Overview (USE)** | node CPU/mem/disk/net, pod count vs capacity, requests vs allocatable (overcommit %) | node-exporter, kube-state-metrics (KSM) | the EKS console homepage, but honest |
| **2. Workloads & Inventory** (the Rancher replacement) | every running image+tag (`kube_pod_container_info`), deployment/sts replica health, restarts, OOMKills, Pending pods, per-namespace counts | KSM | drift between "what I think runs" and reality |
| **3. GitOps / Flux** | reconcile status per Kustomization/HelmRelease (`gotk_reconcile_condition`), failure durations, last-applied revision, suspended resources | Flux controllers (export Prometheus metrics natively) | deploy-pipeline health — what platform teams stare at |
| **4. Ingress Golden Signals (RED)** | request rate, 4xx/5xx %, p50/p99 latency **per host** (dufeut.com, auth., vpn.) | Traefik metrics (enable its Prometheus endpoint + a scrape config — the one real config change) | THE on-call dashboard everywhere |
| **5. Postgres / CNPG** | connections, TPS, replication, WAL archive status (**backup failures show here**), txn age, slow queries | CNPG instances export metrics natively; add a PodMonitor/scrape | what DBAs watch; pairs with the restore drills |
| **6. Capacity & Saturation** | PVC % used + days-to-full, inode usage, CPU throttling (`container_cpu_cfs_throttled_*`), memory pressure | kubelet/cAdvisor, KSM | the "limits are lies" lesson; capacity planning |
| **7. Certificates & Backups** | cert-manager expiry countdowns, **age of last successful backup** (CNPG + NetBird CronJob), backup job failures | cert-manager metrics, KSM job metrics | the two silent killers in small ops |
| **8. Logs (Loki)** | error-rate panels from logs, per-namespace log volume, app log explorer | Loki+promtail (already running) | metrics tell you *that*, logs tell you *why* |

## Alert pack (each rule names the board it points at)

NodeDown · PodCrashLooping (>3 restarts/15m) · Pending >10m · PVC >80% (warn) / >90% (crit) · CertExpiring <14d · **BackupStale >26h** · FluxReconcileFailing >15m · WAL-archive failing · 5xx >5% over 10m · CPU throttling sustained · clouder (CP) mem >85%.

## Implementation route (fits the existing gitops shape)

1. **Dashboards as code**: JSON files in `gitops/platform/components/monitoring/dashboards/`, mounted via Grafana provisioning (ConfigMaps) — no clicking, PR-reviewed, exactly how big shops version dashboards. Start from community dashboards (kube-state/node-exporter/Flux/CNPG/Traefik have excellent ones), prune to taste, commit pinned JSON.
2. **Scrape additions** (small): Traefik metrics endpoint (k3s HelmChartConfig toggle), CNPG PodMonitor, Flux controllers, cert-manager.
3. **Alertmanager receiver**: currently `none` — wire email (SMTP creds already exist as a secret) or a Telegram/Discord webhook; alerts nobody receives don't exist.
4. Sizing note: all of this runs on srv2 (already pinned); Prometheus retention stays 15d; Loki keeps defaults. No new components — only configuration of what's deployed.

**Out of scope / later:** tracing (Tempo/OTel — add when an app actually emits spans), SLO burn-rate alerts (multiwindow) — the natural "level 2" once board 4 exists, kubecost-style spend views (pointless on flat-rate VPSes, relevant the day AWS bills by the hour).

**Why not just install a Rancher-like UI:** viewers are fine, writers are not (one-writer invariant). This path gives strictly more information than Rancher's pages, in the tool you already run, with zero new cluster-admin surfaces — and dashboard-as-code + alert literacy is precisely the practice that transfers to EKS/big-shop work.
