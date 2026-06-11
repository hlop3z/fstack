# console-api — Spec Delta

## ADDED Requirements

### Requirement: Exactly three HTTP routes, exactly one with side effects
The HTTP interface SHALL expose exactly three API routes plus static file serving:
- `POST /api/run` — body `{"action": <name>, "params": {...}}` → `{"job_id": ...}`. This SHALL be the only route capable of changing anything.
- `GET /api/state` — one JSON document containing the action registry, inventory-derived fleet summary, and current/finished jobs.
- `GET /api/jobs/{id}/logs` — Server-Sent Events stream of the job's output lines, ending when the job terminates.

#### Scenario: Write funnel
- **WHEN** any state-changing operation is requested over HTTP
- **THEN** it is served by `POST /api/run` and by no other route

#### Scenario: Single poll target
- **WHEN** the dashboard refreshes
- **THEN** one `GET /api/state` call returns everything the page renders (actions, fleet, jobs)

#### Scenario: Log streaming via SSE
- **WHEN** a client opens `GET /api/jobs/{id}/logs` for a running job
- **THEN** output lines arrive as SSE `data:` events as they are produced, and the stream closes after the job's terminal state

### Requirement: HTTP adapter is marshalling only
`console/app.py` SHALL contain no action-specific logic — no branching on action names, no validation rules, no danger gating. It SHALL translate HTTP requests to core calls and core results/errors to HTTP responses (validation error → 400, target busy → 409, unknown job → 404).

#### Scenario: Logic-leak tripwire
- **WHEN** the implementation of `app.py` is reviewed
- **THEN** it contains no `if action == ...` style branches; all decisions trace to `console/core/`

### Requirement: Server binds to loopback only
The server SHALL bind `127.0.0.1` (never `0.0.0.0`) when run directly, and the dashboard SHALL be served by the same process at `/`. There SHALL be no authentication layer in the spike — localhost binding is the access control, and adding auth to enable remote exposure is out of scope.

#### Scenario: Not reachable from the network
- **WHEN** another machine on the LAN attempts to connect to port 8080 (with the console running bare, not containerized)
- **THEN** the connection is refused because the socket is bound to loopback

### Requirement: Dashboard is a single static page with vendored assets
The UI SHALL be one `index.html` using a vendored, version-pinned `alpine.min.js` static file; styling SHALL be hand-authored CSS within the page (no CSS framework). The frontend SHALL require no Node.js, npm, package.json, or build step. The page SHALL render the fleet/action/jobs state from `GET /api/state`, trigger actions via `POST /api/run` (with a confirmation dialog for `DISRUPTIVE` and typed-name confirmation for `DESTRUCTIVE`), and show live logs from the SSE route.

#### Scenario: No toolchain
- **WHEN** the repository is inspected
- **THEN** no `package.json`, lockfile, or bundler config exists; the JS/CSS assets are committed static files

#### Scenario: Disruptive action confirmation
- **WHEN** the operator clicks a `DISRUPTIVE` action button
- **THEN** the UI requires a confirmation interaction before issuing `POST /api/run`
