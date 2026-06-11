"""Inventory names from the target repo, via Ansible itself.

Ansible is the inventory authority — we shell out to `ansible-inventory --list`
rather than parsing YAML ourselves. The result is the closed set of valid
host/group names used for param validation (which doubles as the
command-injection guard).
"""

import json
import os
import subprocess
import time
from pathlib import Path

_CACHE_TTL_SECONDS = 30.0
_cache: tuple[float, frozenset[str], dict] | None = None


def target_dir() -> Path:
    """The repo the console operates on (mounted at /work in the container)."""
    return Path(os.environ.get("CONSOLE_TARGET_DIR", ".")).resolve()


def _load(refresh: bool = False) -> tuple[frozenset[str], dict]:
    global _cache
    now = time.monotonic()
    if not refresh and _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1], _cache[2]

    proc = subprocess.run(
        ("ansible-inventory", "--list"),
        cwd=target_dir(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ansible-inventory failed: {proc.stderr.strip()[:500]}")

    data = json.loads(proc.stdout)
    names: set[str] = set()
    host_tags: dict[str, list[str]] = {}
    groups: list[str] = []
    for group, value in data.items():
        if group == "_meta":
            for h in value.get("hostvars", {}):
                host_tags.setdefault(h, [])
            names.update(value.get("hostvars", {}))
        else:
            names.add(group)
            if group not in ("all", "ungrouped"):
                groups.append(group)
            if isinstance(value, dict):
                for h in value.get("hosts", ()):
                    names.add(h)
                    if group not in ("all", "ungrouped"):
                        host_tags.setdefault(h, []).append(group)

    structure = {
        "hosts": [{"name": h, "tags": sorted(t)} for h, t in sorted(host_tags.items())],
        "groups": sorted(groups),
    }
    _cache = (now, frozenset(names), structure)
    return _cache[1], _cache[2]


def load_names(refresh: bool = False) -> frozenset[str]:
    """Host and group names known to the target repo's inventory (validation set)."""
    return _load(refresh)[0]


def structure(refresh: bool = False) -> dict:
    """Hosts with their tag (group) memberships, for the fleet board."""
    return _load(refresh)[1]
