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
_cache: tuple[float, frozenset[str]] | None = None


def target_dir() -> Path:
    """The repo the console operates on (mounted at /work in the container)."""
    return Path(os.environ.get("CONSOLE_TARGET_DIR", ".")).resolve()


def load_names(refresh: bool = False) -> frozenset[str]:
    """Host and group names known to the target repo's inventory."""
    global _cache
    now = time.monotonic()
    if not refresh and _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]

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
    for group, value in data.items():
        if group == "_meta":
            names.update(value.get("hostvars", {}))
        else:
            names.add(group)
            if isinstance(value, dict):
                names.update(value.get("hosts", ()))
    _cache = (now, frozenset(names))
    return _cache[1]
