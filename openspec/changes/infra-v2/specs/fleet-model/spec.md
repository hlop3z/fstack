# fleet-model — Spec Delta

## ADDED Requirements

### Requirement: fleet.yml is the single L0 source of truth
The system SHALL define the entire fleet in one hand-authored `fleet.yml`: per host a name, public address, optional ssh_port, and a set of tags. Tags SHALL describe host-level traits only (`cp`, `worker`, and future traits like `canary`); workload composition SHALL NOT be expressed as tags (it lives in the gitops tree).

#### Scenario: One screen describes the fleet
- **WHEN** an operator opens `fleet.yml`
- **THEN** all hosts (clouder, srv1, srv2), their addresses, and their roles are visible in a single short document

#### Scenario: Workload tags are rejected
- **WHEN** a review finds a tag naming a workload (e.g. `postgres`)
- **THEN** it is moved to the gitops cell composition; tags remain host traits only

### Requirement: Ansible inventory is generated, never authored
The Ansible inventory SHALL be derived from `fleet.yml` by a small stdlib-Python generator producing one group per tag plus `all`. Hand-editing the generated inventory SHALL be treated as a defect; the generator is idempotent and runs as a console/CLI action.

#### Scenario: Tag-to-group derivation
- **WHEN** `fleet.yml` tags clouder `[cp]` and srv1/srv2 `[worker]`
- **THEN** the generated inventory contains group `cp` = {clouder} and group `worker` = {srv1, srv2}, with `ansible_host` set from the address field

#### Scenario: Adding a host
- **WHEN** a new host entry is added to `fleet.yml` and the generator runs
- **THEN** no other file requires editing for the host to be targetable by tag-selected playbooks

### Requirement: Only the fleet file knows where a host came from
No role, playbook, or gitops manifest SHALL hardcode provider-specific host facts (Hostinger IPs, DC names). Provider knowledge SHALL be confined to `fleet.yml`, preserving the future Terraform handoff (generator consumes Terraform output instead — same schema).

#### Scenario: Provider swap dry-run
- **WHEN** a host's address changes in `fleet.yml` and the generator + playbooks re-run
- **THEN** no other file requires a provider-related edit
