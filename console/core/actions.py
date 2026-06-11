"""The action registry: the single definition of the console's operational surface.

Adding an action means adding an entry to REGISTRY and nothing else — both the
CLI and the HTTP API pick it up automatically. Adapters must never branch on
action names.

argv templates use {param} placeholders. Values are rendered only after
validation against the closed inventory set (see service.py) — free text never
reaches argv, and no shell is ever involved.
"""

from dataclasses import dataclass, field
from enum import Enum, auto


class Danger(Enum):
    SAFE = auto()  # one click / no confirmation
    DISRUPTIVE = auto()  # changes host state — UI confirm dialog
    DESTRUCTIVE = auto()  # removes things — requires typed target confirmation


@dataclass(frozen=True)
class Action:
    name: str
    argv: tuple[str, ...]  # may contain {param} placeholders
    params: tuple[str, ...] = ()  # params rendered into argv, validated against inventory
    danger: Danger = Danger.SAFE
    description: str = ""
    # Busy-lock key. "{<param>}" locks per rendered param value; a literal string
    # locks globally for that key (e.g. all fleet-wide actions share "fleet").
    target: str = "fleet"


_BUILTINS: tuple[Action, ...] = (
    Action(
        name="fleet:ping",
        argv=("ansible", "all", "-m", "ping"),
        danger=Danger.SAFE,
        description="SSH reachability check for every host in the inventory",
        target="fleet",
    ),
    Action(
        name="inventory:show",
        argv=("ansible-inventory", "--graph"),
        danger=Danger.SAFE,
        description="Render the inventory tree (local read, no SSH)",
        target="inventory",
    ),
)


def _target_actions() -> tuple[Action, ...]:
    """Actions declared by the TARGET repo in console.actions.yml — the image stays
    generic; each fleet/config repo brings its own operational surface."""
    import os
    from pathlib import Path

    import yaml

    path = Path(os.environ.get("CONSOLE_TARGET_DIR", ".")) / "console.actions.yml"
    if not path.is_file():
        return ()
    spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return tuple(
        Action(
            name=a["name"],
            argv=tuple(a["argv"]),
            params=tuple(a.get("params", ())),
            danger=Danger[a.get("danger", "DISRUPTIVE").upper()],
            description=a.get("description", ""),
            target=a.get("target", "fleet"),
        )
        for a in spec.get("actions", ())
    )


REGISTRY: dict[str, Action] = {a.name: a for a in (*_BUILTINS, *_target_actions())}
