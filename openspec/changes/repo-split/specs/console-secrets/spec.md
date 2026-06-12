## ADDED Requirements

### Requirement: Target repo declares its secret surface
The console MUST read secret-management configuration exclusively from the target repo's `console.actions.yml` `secrets:` section (SOPS file path, encrypted-suffix list, derived-secret render map). The public tool repo MUST contain no fleet-specific key names, file paths, or render mappings.

#### Scenario: Manifest drives behavior
- **WHEN** the console runs `secret list` against a target repo whose manifest declares `file: infra/secrets/infra.sops.yaml`
- **THEN** it decrypts and lists key names from that file, without any tool-side configuration

#### Scenario: Missing manifest fails clearly
- **WHEN** the target repo's `console.actions.yml` has no `secrets:` section
- **THEN** `console secret` commands exit non-zero with a message explaining what the target repo must declare

### Requirement: Generic secret subcommand with plaintext guard
The console MUST provide `secret set|get|list|rm`. `set` MUST refuse key names that do not match the target repo's declared encrypted suffixes unless explicitly confirmed, MUST support a hidden prompt (value never in argv/history), and MUST verify the file remains SOPS-encrypted after writing.

#### Scenario: Suffix guard blocks plaintext-bound keys
- **WHEN** `secret set my_setting` is invoked and `my_setting` matches no declared encrypted suffix
- **THEN** the console warns it would be stored in plaintext and aborts without confirmation

#### Scenario: Hidden prompt
- **WHEN** `secret set ghcr_pull_token` is invoked with no value argument
- **THEN** the value is read from a non-echoing prompt and the resulting file contains the key encrypted

### Requirement: Derived secrets re-render on set
WHEN a key set via `secret set` appears in the manifest's `derived:` map, the console MUST run the mapped ops action so the dependent gitops Secret is re-rendered in the same operation, and MUST tell the operator to commit the result.

#### Scenario: Rotation is one command
- **WHEN** `secret set ghcr_pull_token` completes and the manifest maps it to `ghcr-pull-secret`
- **THEN** the render action runs and the rendered `*.sops.yaml` in the target repo is updated and still encrypted
