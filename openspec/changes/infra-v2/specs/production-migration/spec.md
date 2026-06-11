# production-migration — Spec Delta

## ADDED Requirements

### Requirement: Every stateful service migrates restore-first
No stateful service SHALL be cut over by data copy alone: each (CNPG Postgres, Garage objects, Zitadel via its database, NetBird state) SHALL be restored into the new cluster from its backup and verified there (application-level check, not just pod-Running) while v1 still holds the originals.

#### Scenario: Postgres proven before cutover
- **WHEN** CNPG restores the production database from S3 into the new cluster
- **THEN** a verification query (row counts / app smoke test against the restored DB) passes before any DNS or app cutover

### Requirement: Worker rebuild order is srv2 first, then srv1
srv2 SHALL be drained from v1, rebuilt, and joined to the new cluster first; production workloads are restored and cut over there while srv1 continues running v1 as the rollback anchor. srv1 SHALL be rebuilt only after the new cluster has served production traffic through a verification window.

#### Scenario: Rollback remains possible mid-migration
- **WHEN** the new cluster misbehaves after srv2's cutover
- **THEN** v1 on srv1 still holds the app + data and DNS can flip back without data loss (writes during the window are reconciled or the window is kept read-only/short)

### Requirement: Cutover is a DNS flip with explicit gates
Cutover SHALL occur only after, in order: MTU gate passed, platform components healthy, stateful restores verified, app smoke test green on the new cluster. The flip is Cloudflare records moving to the new ingress; TLS SHALL be serving on the new cluster before the flip.

#### Scenario: Gated flip
- **WHEN** any gate is unmet
- **THEN** DNS does not move and the migration pauses at the failed gate

### Requirement: v1 is decommissioned terminally, not left coexisting
After the verification window, srv1 SHALL be rebuilt and joined as the second worker, and `ansible-01` SHALL be archived read-only (final commit documenting the migration). Two-engine/two-topology coexistence — v1's disease — SHALL NOT persist past this change.

#### Scenario: Clean end state
- **WHEN** the change completes
- **THEN** the fleet runs only the new cluster, Flux is the only Day-2 engine, and ansible-01's repo is archived with no live consumers
