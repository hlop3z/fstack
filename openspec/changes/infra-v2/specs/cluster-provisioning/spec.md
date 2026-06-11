# cluster-provisioning — Spec Delta

## ADDED Requirements

### Requirement: k3s roles install by tag over the NetBird underlay
A `k3s_cp` role SHALL install the k3s server on `cp`-tagged hosts and a `k3s_worker` role SHALL join `worker`-tagged hosts, with every node's `--node-ip` set to its NetBird `wt0` address so all node↔node and pod↔pod traffic rides WireGuard. The k3s version SHALL be pinned.

#### Scenario: Tag-driven cluster build
- **WHEN** the cluster playbook runs against the fleet
- **THEN** clouder (tag `cp`) runs the k3s server and srv1/srv2 (tag `worker`) join as agents, all using 100.x node IPs

### Requirement: The control plane is tainted and reachable without the mesh
The CP node SHALL be tainted `NoSchedule` so only tolerating workloads (NetBird mgmt, CP-adjacent components) run there, protecting its 1 vCPU / 4 GB. The k3s API SHALL advertise both the public and `wt0` addresses (`tls-san`), so the CP never depends on the mesh to reach itself and the operator's kubeconfig works from outside the mesh.

#### Scenario: General workloads avoid the CP
- **WHEN** a deployment without a CP toleration is scheduled
- **THEN** its pods land only on worker nodes

#### Scenario: Mesh-down API access
- **WHEN** the NetBird mesh is degraded
- **THEN** `kubectl` against the CP's public address still works

### Requirement: MTU verification gates the cluster into service
Before any workload migrates, a large-payload test (iperf or equivalent pod-to-pod across the srv1 WAN link) SHALL pass without black-holing. This gate is mandatory — v1's WireGuard failures were MTU/offload pathologies discovered too late.

#### Scenario: Black-hole detected early
- **WHEN** the large-payload test fails across any node pair
- **THEN** the cluster is not promoted; MTU/offload is fixed (or the documented site-model fallback is invoked) before proceeding

### Requirement: Flux bootstrap completes L1
The CP role SHALL end by installing Flux pointed at this repo's `gitops/clusters/prod/` path and creating the SOPS age-key Secret. From that moment, the L1→L2 contract holds: Ansible never applies Kubernetes manifests (v1's `security-netpol.yml` pattern is structurally dead).

#### Scenario: Layer contract enforced
- **WHEN** the cluster playbook finishes
- **THEN** Flux is reconciling `gitops/clusters/prod/` and no playbook contains `kubectl apply`/`helm install` tasks
