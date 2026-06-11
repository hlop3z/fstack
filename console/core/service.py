"""Core entry points. ALL decisions live here (or deeper) — never in adapters.

run() pipeline: registry lookup -> param validation against the closed
inventory set -> danger gate -> spawn job. Adapters only marshal.
"""

import re

from . import inventory, jobs
from .actions import REGISTRY, Action, Danger
from .errors import ConfirmationRequired, InvalidParam, InventoryUnavailable, UnknownAction

CONFIRM_PARAM = "confirm"  # DESTRUCTIVE actions require confirm=<target value>


def _validate(action: Action, params: dict[str, str], valid_names: frozenset[str]) -> dict[str, str]:
    extra = set(params) - set(action.params) - {CONFIRM_PARAM}
    if extra:
        raise InvalidParam(f"unexpected parameter(s): {', '.join(sorted(extra))}")
    choices = dict(action.choices)
    patterns = dict(action.patterns)
    rendered: dict[str, str] = {}
    for name in action.params:
        value = params.get(name)
        if value is None:
            raise InvalidParam(f"missing parameter: {name}")
        # Exactly one validation path, each a closed/strict set — the injection guard.
        if name in choices:
            if value not in choices[name]:
                raise InvalidParam(f"{name}={value!r} not in {list(choices[name])}")
        elif name in patterns:
            if not re.fullmatch(patterns[name], value):
                raise InvalidParam(f"{name}={value!r} does not match {patterns[name]!r}")
        elif value not in valid_names:
            raise InvalidParam(f"{name}={value!r} is not a known inventory host/group")
        rendered[name] = value
    return rendered


def _target(action: Action, rendered: dict[str, str]) -> str:
    return action.target.format(**rendered)


async def run(
    action_name: str,
    params: dict[str, str] | None = None,
    *,
    valid_names: frozenset[str] | None = None,  # injectable for tests
    registry: dict[str, Action] | None = None,  # injectable for tests
) -> jobs.Job:
    params = params or {}
    registry = registry if registry is not None else REGISTRY
    action = registry.get(action_name)
    if action is None:
        raise UnknownAction(f"no such action: {action_name}")

    if valid_names is None:
        # Only the inventory-validated params need the inventory loaded; an action
        # whose params are all choices/patterns must work even without SSH/inventory.
        special = {p for p, _ in action.choices} | {p for p, _ in action.patterns}
        if any(p not in special for p in action.params):
            try:
                valid_names = inventory.load_names()
            except Exception as exc:
                raise InventoryUnavailable(f"cannot load inventory: {exc}") from exc
        else:
            valid_names = frozenset()
    rendered = _validate(action, params, valid_names)
    target = _target(action, rendered)

    if action.danger is Danger.DESTRUCTIVE and params.get(CONFIRM_PARAM) != target:
        raise ConfirmationRequired(
            f"destructive action: pass {CONFIRM_PARAM}={target} to confirm"
        )

    argv = tuple(part.format(**rendered) for part in action.argv)
    return await jobs.start(action.name, target, argv, cwd=str(inventory.target_dir()))


def get_job(job_id: str) -> jobs.Job:
    return jobs.get(job_id)


def snapshot() -> dict:
    """Everything the dashboard renders, in one document (the page's single poll target)."""
    try:
        fleet = sorted(inventory.load_names())
        fleet_detail = inventory.structure()
        fleet_error = None
    except Exception as exc:  # inventory unavailable must not take down /api/state
        fleet, fleet_detail, fleet_error = [], {"hosts": [], "groups": []}, str(exc)
    return {
        "actions": [
            {
                "name": a.name,
                "description": a.description,
                "danger": a.danger.name,
                "params": list(a.params),
                # how each param should be entered: a closed list -> dropdown,
                # a regex -> validated text box, neither -> pick a fleet host
                "choices": {k: list(v) for k, v in a.choices},
                "patterns": {k: v for k, v in a.patterns},
            }
            for a in REGISTRY.values()
        ],
        "fleet": fleet,
        "fleet_detail": fleet_detail,
        "fleet_error": fleet_error,
        "jobs": [j.summary() for j in jobs.all_jobs()],
    }
