"""Interface adapter #1: argparse -> core. No decisions here — parsing and printing only.

DESTRUCTIVE confirmation is a plain `confirm=<target>` parameter (non-interactive,
scriptable); the gate itself is enforced by the core, identically for the HTTP API.
"""

import argparse
import asyncio
import sys

from . import core
from .core.actions import REGISTRY


def _cmd_list() -> int:
    width = max(len(name) for name in REGISTRY)
    for action in REGISTRY.values():
        print(f"{action.name:<{width}}  {action.danger.name:<11}  {action.description}")
    return 0


async def _cmd_run(action_name: str, pairs: list[str]) -> int:
    params: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            print(f"error: parameters must be key=value, got {pair!r}", file=sys.stderr)
            return 2
        params[key] = value

    try:
        job = await core.run(action_name, params)
    except core.ConsoleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    async for line in job.stream():
        print(line)
    return job.exit_code if job.exit_code is not None else 1


def _cmd_serve(host: str, port: int) -> int:
    import uvicorn  # imported here so core/CLI work without it installed

    uvicorn.run("console.app:app", host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console", description="Infra console (spike)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show all actions")

    p_run = sub.add_parser("run", help="run an action and stream its output")
    p_run.add_argument("action")
    p_run.add_argument("params", nargs="*", metavar="key=value")

    p_serve = sub.add_parser("serve", help="start the dashboard (loopback only)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)

    args = parser.parse_args(argv)
    if args.command == "list":
        return _cmd_list()
    if args.command == "run":
        return asyncio.run(_cmd_run(args.action, args.params))
    if args.command == "serve":
        return _cmd_serve(args.host, args.port)
    return 2
