"""Repo-agnostic SOPS secret management, driven by the TARGET repo's manifest.

The console knows NOTHING about any fleet's secrets. The target repo declares its
secret surface in console.actions.yml:

    secrets:
      file: infra/secrets/infra.sops.yaml      # SOPS-encrypted key/value file
      encrypted_suffixes: [_token, _key, ...]  # names the repo's .sops.yaml encrypts
      derived:                                  # key -> CONSOLE ACTION that re-renders
        ghcr_pull_token: image:ghcr-pull-secret #   the gitops Secret this key feeds
        alertmanager_discord_webhook: alerts:set-discord

Why suffixes matter: the target repo's .sops.yaml encrypted_regex selects WHICH keys
get encrypted by NAME. A key outside the convention would be written in PLAINTEXT and
committed — `set` refuses those unless forced. After every write we verify the value
does not appear in the raw file (the leak guard).

Derived secrets: the cluster never reads the source-of-truth file — it reads gitops-
rendered Secrets. `derived` maps a key to the console action that re-renders its
artifact, so rotation is one command. The action runs through the normal registry
(locks, validation, streaming) — this module stays ignorant of what rendering means.
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConsoleError


class SecretsUnconfigured(ConsoleError):
    """The target repo declares no secrets: manifest."""


class PlaintextRefused(ConsoleError):
    """Key name matches no encrypted suffix — would be committed in plaintext."""


@dataclass(frozen=True)
class SecretsManifest:
    file: Path  # absolute path to the sops file inside the target repo
    encrypted_suffixes: tuple[str, ...]
    derived: dict[str, str] = field(default_factory=dict)  # key -> console action name


def _target_dir() -> Path:
    return Path(os.environ.get("CONSOLE_TARGET_DIR", "."))


def load_manifest() -> SecretsManifest:
    import yaml

    root = _target_dir()
    path = root / "console.actions.yml"
    spec = {}
    if path.is_file():
        spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = spec.get("secrets")
    if not section or "file" not in section:
        raise SecretsUnconfigured(
            "the target repo declares no secret surface — add to console.actions.yml:\n"
            "  secrets:\n"
            "    file: <path/to/secrets.sops.yaml>\n"
            "    encrypted_suffixes: [_token, _key, _webhook, _password, _secret]\n"
            "    derived: {<key>: <console action that re-renders it>}"
        )
    return SecretsManifest(
        file=root / section["file"],
        encrypted_suffixes=tuple(section.get("encrypted_suffixes", ())),
        derived=dict(section.get("derived") or {}),
    )


def _sops(args: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(["sops", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ConsoleError(f"sops failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def _decrypted(manifest: SecretsManifest) -> dict:
    import yaml

    out = _sops(["-d", str(manifest.file)]).stdout
    return yaml.safe_load(out) or {}


def list_keys(manifest: SecretsManifest) -> list[str]:
    return sorted(str(k) for k in _decrypted(manifest))


def get(manifest: SecretsManifest, key: str) -> str:
    data = _decrypted(manifest)
    if key not in data:
        raise ConsoleError(f"no such key: {key}")
    return str(data[key])


def matches_suffix(manifest: SecretsManifest, key: str) -> bool:
    return any(key.endswith(s) for s in manifest.encrypted_suffixes)


def set_value(manifest: SecretsManifest, key: str, value: str, force: bool = False) -> None:
    """Write one key. Refuses plaintext-bound names unless forced; verifies the
    value is not readable in the raw file afterwards (the actual leak check)."""
    if not force and manifest.encrypted_suffixes and not matches_suffix(manifest, key):
        raise PlaintextRefused(
            f"{key!r} matches none of {list(manifest.encrypted_suffixes)} — the target "
            "repo's .sops.yaml would store it in PLAINTEXT. Rename it to a convention "
            "suffix, or pass --force if plaintext is intended."
        )
    _sops(["set", str(manifest.file), f'["{key}"]', _json_string(value)])
    raw = manifest.file.read_text(encoding="utf-8")
    if value and value in raw:
        raise ConsoleError(
            f"LEAK GUARD: the value of {key!r} is readable in {manifest.file.name} after "
            "writing — the repo's .sops.yaml does not encrypt this key. Reverting is on "
            "you (git checkout the file); fix the encrypted_regex before retrying."
        )


def unset(manifest: SecretsManifest, key: str) -> None:
    _sops(["unset", str(manifest.file), f'["{key}"]'])


def _json_string(value: str) -> str:
    import json

    return json.dumps(value)


def open_all(manifest: SecretsManifest) -> dict:
    """Full decrypted key/value map — the source of truth, for bulk edit. The plaintext
    must stay ephemeral in the caller (temp outside any synced dir, or in-memory only)."""
    return _decrypted(manifest)


def save_all(manifest: SecretsManifest, new: dict, force: bool = False) -> list[str]:
    """Reconcile the whole secret set to `new`: write changed keys, drop removed ones,
    and RETURN the distinct `derived` actions to re-render (the adapter runs them — this
    layer stays ignorant of jobs). Validates every new/changed name up front so a
    plaintext-bound name aborts the save BEFORE any write (no partial writes)."""
    old = _decrypted(manifest)
    norm = {str(k): (v if isinstance(v, str) else str(v)) for k, v in (new or {}).items()}
    changed = {k: v for k, v in norm.items() if old.get(k) != v}
    removed = [k for k in old if k not in norm]

    if not force and manifest.encrypted_suffixes:
        bad = [k for k in changed if not matches_suffix(manifest, k)]
        if bad:
            raise PlaintextRefused(
                f"{bad} match none of {list(manifest.encrypted_suffixes)} — the target "
                "repo's .sops.yaml would store them in PLAINTEXT. Rename to a convention "
                "suffix, or pass force."
            )

    for key, value in changed.items():
        set_value(manifest, key, value, force=True)  # names already validated above
    for key in removed:
        unset(manifest, key)

    actions: list[str] = []
    for key in [*changed, *removed]:
        action = manifest.derived.get(key)
        if action and action not in actions:
            actions.append(action)
    return actions
