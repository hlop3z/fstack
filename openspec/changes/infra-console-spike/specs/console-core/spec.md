# console-core — Spec Delta

## ADDED Requirements

### Requirement: Action registry is the single definition of the operational surface
The system SHALL define all runnable actions in a single registry module (`console/core/actions.py`). Each action SHALL declare: a unique kebab/colon name, an argv template, named parameters, a danger level (`SAFE`, `DISRUPTIVE`, or `DESTRUCTIVE`), and a human-readable description. The spike SHALL ship exactly three actions: `fleet:ping` (SAFE), `fleet:facts` or equivalent read-only status action (SAFE), and `host:update` executed in Ansible `--check` mode (DISRUPTIVE).

#### Scenario: Adding an action requires touching only the registry
- **WHEN** a developer adds a new entry to the registry
- **THEN** the action becomes available in both the CLI (`list`) and the HTTP API (`GET /api/state`) without modifying `cli.py` or `app.py`

#### Scenario: Unknown action is rejected
- **WHEN** a run is requested for a name not present in the registry
- **THEN** the core raises a validation error and no process is spawned

### Requirement: Parameters are validated against the inventory before spawning
The core SHALL validate every action parameter against a closed set derived from the target repo's Ansible inventory (host names, group names). Free-form strings SHALL NOT be interpolated into argv.

#### Scenario: Valid host parameter
- **WHEN** `host:update` is requested with `host=srv1` and `srv1` exists in the inventory
- **THEN** the argv is rendered and the job starts

#### Scenario: Injection attempt is rejected
- **WHEN** an action is requested with a parameter value not present in the inventory (e.g., `srv1; rm -rf /`)
- **THEN** the core rejects the request with a validation error and no process is spawned

### Requirement: Runner spawns processes and streams output lines
The core SHALL run actions via `asyncio` subprocess execution (no shell), exposing an async iterator of output lines (stdout and stderr merged or labeled) and a final exit code on the job handle.

#### Scenario: Live line streaming
- **WHEN** a job is running
- **THEN** consumers can iterate output lines as they are produced, without waiting for process exit

#### Scenario: Exit code reported
- **WHEN** the spawned process exits
- **THEN** the job records the exit code and transitions to a terminal state (`succeeded` on 0, `failed` otherwise)

### Requirement: One concurrent job per target
The core SHALL maintain an in-memory job table and SHALL refuse to start a job whose target (host/group) already has a running job, returning a busy error instead of queuing.

#### Scenario: Double-run refused
- **WHEN** `host:update host=srv1` is requested while another job against `srv1` is running
- **THEN** the core refuses with a "target busy" error and the running job is unaffected

### Requirement: Core is stateless across restarts and free of interface imports
The core SHALL hold no persistent state (no database, no files written for its own purposes); job history SHALL be in-memory only and lost on restart by design. Modules under `console/core/` SHALL NOT import FastAPI, uvicorn, argparse wiring, or any Docker-related library.

#### Scenario: Restart loses only history
- **WHEN** the console process is killed and restarted
- **THEN** it serves the same actions and fleet state, with an empty job history, and nothing else is lost

#### Scenario: Import isolation holds
- **WHEN** `console/core/*` modules are imported in a bare Python environment without FastAPI installed
- **THEN** the import succeeds
