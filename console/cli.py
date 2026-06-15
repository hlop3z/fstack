"""Interface adapter #1: argparse -> core. No decisions here — parsing and printing only.

DESTRUCTIVE confirmation is a plain `confirm=<target>` parameter (non-interactive,
scriptable); the gate itself is enforced by the core, identically for the HTTP API.
"""

import argparse
import asyncio
import sys

from . import core
from .core.actions import REGISTRY


def _shred(path: str) -> None:
    """Best-effort wipe of an ephemeral plaintext temp: overwrite, then unlink."""
    import os

    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as fh:
            fh.write(b"\0" * size)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass
    try:
        os.unlink(path)
    except OSError:
        pass


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


async def _cmd_secret(args) -> int:
    from .core import secrets

    try:
        manifest = secrets.load_manifest()
        if args.secret_command == "list":
            for key in secrets.list_keys(manifest):
                print(key)
            return 0
        if args.secret_command == "get":
            print(secrets.get(manifest, args.key))
            return 0
        if args.secret_command == "rm":
            secrets.unset(manifest, args.key)
            print(f"removed {args.key}")
            return 0
        if args.secret_command == "set":
            value = args.value
            if value is None:
                import getpass

                value = getpass.getpass(f"value for {args.key} (hidden): ")
            secrets.set_value(manifest, args.key, value, force=args.force)
            print(f"set {args.key} (encrypted)")
            # Derived secret: re-render the gitops artifact this key feeds, via the
            # target repo's own declared action — rotation stays one command.
            action = manifest.derived.get(args.key)
            if action:
                print(f">> re-rendering via {action} …")
                rc = await _cmd_run(action, [])
                if rc == 0:
                    print(">> done — commit & push the target repo so Flux applies it")
                return rc
            return 0
        if args.secret_command == "edit":
            import os
            import shlex
            import subprocess
            import tempfile

            import yaml

            data = secrets.open_all(manifest)
            fd, tmp = tempfile.mkstemp(suffix=".sops-edit.yaml", dir=tempfile.gettempdir())
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    yaml.safe_dump(data, fh, sort_keys=True, default_flow_style=False)
                try:
                    os.chmod(tmp, 0o600)  # POSIX; Windows ACLs differ (local box only)
                except OSError:
                    pass
                editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "vi")
                subprocess.call(shlex.split(editor) + [tmp])
                with open(tmp, encoding="utf-8") as fh:
                    new = yaml.safe_load(fh) or {}
            finally:
                _shred(tmp)  # ephemeral plaintext never persists
            if new == data:
                print("no changes")
                return 0
            actions = secrets.save_all(manifest, new, force=args.force)
            print("saved (encrypted)")
            for action in actions:
                print(f">> re-rendering via {action} …")
                rc = await _cmd_run(action, [])
                if rc != 0:
                    return rc
            if actions:
                print(">> done — commit & push the target repo so Flux applies it")
            return 0
    except core.ConsoleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


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

    p_secret = sub.add_parser(
        "secret", help="manage the target repo's SOPS secrets (manifest-driven)"
    )
    sec = p_secret.add_subparsers(dest="secret_command", required=True)
    sec.add_parser("list", help="key names only")
    s_get = sec.add_parser("get", help="print one value")
    s_get.add_argument("key")
    s_rm = sec.add_parser("rm", help="delete a key")
    s_rm.add_argument("key")
    s_set = sec.add_parser("set", help="set a key (hidden prompt if no value given)")
    s_set.add_argument("key")
    s_set.add_argument("value", nargs="?", default=None)
    s_set.add_argument(
        "--force", action="store_true", help="allow a name outside the encrypted suffixes"
    )
    s_edit = sec.add_parser(
        "edit", help="edit ALL keys in $EDITOR (ephemeral temp; re-encrypt + render derived)"
    )
    s_edit.add_argument(
        "--force", action="store_true", help="allow names outside the encrypted suffixes"
    )

    args = parser.parse_args(argv)
    if args.command == "list":
        return _cmd_list()
    if args.command == "run":
        return asyncio.run(_cmd_run(args.action, args.params))
    if args.command == "serve":
        return _cmd_serve(args.host, args.port)
    if args.command == "secret":
        return asyncio.run(_cmd_secret(args))
    return 2
