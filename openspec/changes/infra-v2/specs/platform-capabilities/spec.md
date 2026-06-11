# platform-capabilities — Spec Delta

## ADDED Requirements

### Requirement: Each capability is a self-contained kustomize component
The platform SHALL provide components: `postgres` (CNPG operator + cluster), `s3` (Garage), `redis`, `mq` (RabbitMQ), `oidc` (Zitadel), `monitoring` (Prometheus/Grafana/Alertmanager), and `netbird` (control plane). Each component SHALL carry its own namespace, pinned versions/charts (vendored where v1 vendored), NetworkPolicies, and backup configuration where stateful.

#### Scenario: Component is independently buildable
- **WHEN** `kustomize build` runs on a component with a minimal test root
- **THEN** it produces valid manifests without requiring unrelated components

### Requirement: Placement rules — stateful pinned, stateless floats
Stateful/chatty capabilities (postgres, redis, mq, s3, oidc) SHALL carry nodeSelectors/affinity pinning them to srv2 (same DC as the CP); stateless app replicas SHALL float across workers. This contains the 64 ms WAN hop; a Service crossing it is a placement bug, not a Kubernetes bug.

#### Scenario: Database lands on the near worker
- **WHEN** the postgres component deploys
- **THEN** its pods schedule on srv2 (and never on the WAN-remote worker without an explicit override)

### Requirement: NetBird runs in-cluster with continuity of state
The `netbird` component SHALL run the management/signal/relay stack pinned (with toleration) to the CP node, exposed on the same public endpoints (`vpn.dufeut.com`, STUN 3478/udp), initialized from the restored state so existing peers keep their identities. The interim compose stack SHALL be stopped only after in-cluster NetBird is serving and peers show Connected.

#### Scenario: Peers survive the move
- **WHEN** the in-cluster NetBird takes over from the interim compose
- **THEN** srv1/srv2 (and other peers) reconnect without re-enrollment

### Requirement: Stateful capabilities back up off-host
CNPG SHALL keep S3 backups (v1's Barman setup), and a NetBird state backup CronJob SHALL replace `netbird-backup.yml`, writing the same archive shape to the same S3 prefix. Each backup path SHALL be verified once by an actual restore or round-trip before v1's equivalent is retired.

#### Scenario: Backup parity before retirement
- **WHEN** the in-cluster NetBird backup CronJob's first run completes
- **THEN** its artifact is round-trip verified (download + content check) before the host-level timer is removed
