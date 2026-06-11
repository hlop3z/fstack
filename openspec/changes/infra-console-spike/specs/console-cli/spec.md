# console-cli — Spec Delta

## ADDED Requirements

### Requirement: CLI exposes the full action surface headlessly
The system SHALL provide a command-line interface (`python -m console ...`) over the core with at least: `list` (show all registry actions with danger level and description) and `run <action> [param=value ...]` (execute an action and stream its output to the terminal). The CLI SHALL exit with the job's exit code.

#### Scenario: List actions
- **WHEN** the operator runs `python -m console list`
- **THEN** all registry actions are printed with name, danger level, and description

#### Scenario: Run and stream
- **WHEN** the operator runs `python -m console run fleet:ping`
- **THEN** playbook output lines are printed live, and the CLI process exits with the underlying job's exit code

### Requirement: CLI parity — every GUI capability is CLI-runnable
Every action runnable from the dashboard SHALL be runnable from the CLI with identical effect, because both adapters call the same core entry point. The CLI SHALL function with the GUI process not running.

#### Scenario: Console down, operations unaffected
- **WHEN** the FastAPI server is not running
- **THEN** `python -m console run fleet:ping` still executes successfully via the core

### Requirement: CLI contains no behavior of its own
The CLI adapter SHALL be limited to argument parsing, core invocation, and output printing. Action selection, validation, and danger gating SHALL occur in the core only. `DESTRUCTIVE` actions SHALL require an explicit `--yes-i-mean-it <target-name>` style confirmation flag (no interactive prompt, so it stays scriptable); the gate itself is enforced by the core.

#### Scenario: Danger gate enforced by core, not CLI
- **WHEN** a `DESTRUCTIVE` action is invoked without the confirmation parameter
- **THEN** the core (not the argparse layer) rejects it, and the same rejection occurs via the HTTP API
