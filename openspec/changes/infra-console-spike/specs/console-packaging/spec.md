# console-packaging — Spec Delta

## ADDED Requirements

### Requirement: Single image contains the whole toolchain and no state
One `Dockerfile` SHALL produce an image containing Python, Ansible, the console package, and `openssh-client`, with all versions pinned (digest-pinned base image). The image SHALL contain no secrets, no SSH keys, no inventory, and no repository content — it SHALL be safe to push to a public registry.

#### Scenario: Image is state-free
- **WHEN** the built image's filesystem is inspected
- **THEN** it contains toolchain binaries and the console code only — no keys, no `.env`, no inventory, no playbooks

#### Scenario: Reproducible toolchain
- **WHEN** the image is rebuilt from the same Dockerfile
- **THEN** the same pinned Ansible/Python/console versions are present, independent of the host machine

### Requirement: Compose is the composition root — mounts and ports only
A `compose.yml` SHALL define the runtime wiring and nothing else: bind-mount the target repo (read-write), SSH keys (read-only, from a path outside the repo tree), and publish the GUI port as `127.0.0.1:8080:8080`. A bare `8080:8080` publish (which binds all interfaces) SHALL be treated as a defect.

#### Scenario: Loopback-only publish
- **WHEN** `docker compose up` is running
- **THEN** the dashboard is reachable at `http://127.0.0.1:8080` from the host and is not reachable from other machines on the network

#### Scenario: Keys never enter the image or repo
- **WHEN** the compose file is reviewed
- **THEN** SSH key material is provided exclusively via read-only bind mounts from outside the repository tree

### Requirement: One image, multiple entrypoints (CLI parity in the container)
The image SHALL support: default command = the GUI server; `cli ...` = the headless CLI; and direct `ansible-playbook ...` as a raw escape hatch — all via `docker compose run`/`up` without rebuilding.

#### Scenario: Headless run in the container
- **WHEN** the operator runs `docker compose run --rm console cli run fleet:ping`
- **THEN** the action executes and streams output, with no GUI server involved

#### Scenario: Raw escape hatch
- **WHEN** the operator runs `docker compose run --rm console ansible-playbook playbooks/ping.yml`
- **THEN** Ansible runs directly, proving the console is bypassable

### Requirement: Spike targets ansible-01 read-only
The compose setup SHALL mount the existing `ansible-01` repository as the action target for the spike. The spike SHALL NOT modify any file in `ansible-01`, and the only fleet-touching actions SHALL be `fleet:ping` and `host:update` in `--check` mode.

#### Scenario: No writes to the target repo
- **WHEN** the spike's actions are exercised end-to-end
- **THEN** `git status` in `ansible-01` shows no modifications attributable to the console

### Requirement: Bare-Python fallback remains functional
The console package SHALL be runnable without Docker (`uv venv` / `pip install`, then `python -m console ...` and `uvicorn`), because `core/` and the adapters have no Docker awareness. Docker is the recommended runtime (and the only practical one for Ansible on Windows), not a hard dependency of the code.

#### Scenario: Bare CLI on a Linux host
- **WHEN** the package is installed in a plain venv on a Linux machine with SSH access
- **THEN** `python -m console run fleet:ping` works with no container runtime present
