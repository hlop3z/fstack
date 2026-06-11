# host-provisioning — Spec Delta

## ADDED Requirements

### Requirement: Every host is provisioned by the same roles
All hosts SHALL be provisioned by the role set `base` (apt update/upgrade, SSH hardening, fail2ban, sysctl, swap, unattended-upgrades, timezone) and `firewall`, with zero per-host playbook forks. Host differences SHALL be expressed only through tags and group/host vars derived from them.

#### Scenario: No snowflakes
- **WHEN** `cluster.yml` (the provisioning playbook) runs against any host in the fleet
- **THEN** the same roles execute, parameterized only by tag-derived variables

### Requirement: Firewall rules live in exactly one role
All UFW/firewall logic SHALL live in the single `firewall` role (fixing v1's rules duplicated across 4 playbooks). The role SHALL support a provider-edge mode (skip host firewall where the cloud firewall is authoritative) and SHALL produce symmetric ICMP policy between fleet hosts (fixing the observed srv1→clouder asymmetric filtering).

#### Scenario: Rule change touches one file
- **WHEN** a firewall rule must change (e.g. allow a new port between nodes)
- **THEN** the edit happens in the `firewall` role only and applies fleet-wide on the next run

#### Scenario: Symmetric fleet ICMP
- **WHEN** the firewall role has run on all hosts
- **THEN** every fleet host can ping every other fleet host (both directions)

### Requirement: NetBird client on every host
A `netbird_client` role SHALL install the pinned NetBird client and join the host to the mesh (setup key via SOPS-encrypted secret), producing a `wt0` interface. The role SHALL be idempotent and safe to run on a host already joined.

#### Scenario: Fresh host joins the mesh
- **WHEN** the role runs on a newly provisioned host
- **THEN** `wt0` exists with a 100.x address and the peer shows Connected in the NetBird management API

#### Scenario: Re-run is a no-op
- **WHEN** the role runs on an already-joined host
- **THEN** the mesh session is not disturbed (no re-enrollment, no key churn)
