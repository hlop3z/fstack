"""Core tests — stdlib unittest only. Run: python -m unittest discover tests -v"""

import subprocess
import sys
import unittest

from console.core import (
    ConfirmationRequired,
    InvalidParam,
    TargetBusy,
    UnknownAction,
    service,
)
from console.core.actions import Action, Danger

NAMES = frozenset({"web-01", "web-02", "workers"})

# Test registry: argv uses the current interpreter so tests run anywhere.
SLEEP = Action(
    name="test:sleep",
    argv=(sys.executable, "-c", "import time; time.sleep(1.0)"),
    params=("host",),
    target="{host}",
)
ECHO = Action(
    name="test:echo",
    argv=(sys.executable, "-c", "print('line-a'); print('line-b')"),
    target="echo",
)
NUKE = Action(
    name="test:nuke",
    argv=(sys.executable, "-c", "print('boom')"),
    params=("host",),
    danger=Danger.DESTRUCTIVE,
    target="{host}",
)
CREDS = Action(
    name="test:creds",
    argv=(sys.executable, "-c", "print('cred')"),
    params=("service",),
    choices=(("service", ("grafana", "garage")),),
    target="creds-{service}",
)
BUCKET = Action(
    name="test:bucket",
    argv=(sys.executable, "-c", "print('bucket')"),
    params=("name",),
    patterns=(("name", r"^[a-z][a-z0-9-]{1,30}$"),),
    target="bucket-{name}",
)
REGISTRY = {a.name: a for a in (SLEEP, ECHO, NUKE, CREDS, BUCKET)}


class ParamModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_choices_enforced(self):
        # a choice param must NOT be validated against inventory, and rejects off-list
        with self.assertRaises(InvalidParam):
            await service.run("test:creds", {"service": "redis"}, valid_names=NAMES, registry=REGISTRY)
        job = await service.run("test:creds", {"service": "grafana"}, valid_names=frozenset(), registry=REGISTRY)
        async for _ in job.stream():
            pass
        self.assertEqual(job.exit_code, 0)

    async def test_pattern_enforced_and_injection_safe(self):
        for evil in ("Bad Name", "x; rm -rf /", "$(reboot)", "a/b", "UPPER"):
            with self.assertRaises(InvalidParam, msg=evil):
                await service.run("test:bucket", {"name": evil}, valid_names=frozenset(), registry=REGISTRY)
        job = await service.run("test:bucket", {"name": "media-prod"}, valid_names=frozenset(), registry=REGISTRY)
        async for _ in job.stream():
            pass
        self.assertEqual(job.exit_code, 0)


class ValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_action_rejected(self):
        with self.assertRaises(UnknownAction):
            await service.run("no:such:action", {}, valid_names=NAMES, registry=REGISTRY)

    async def test_injection_shaped_param_rejected(self):
        for evil in ("web-01; rm -rf /", "web-01 && whoami", "$(reboot)", "web-01\nweb-02", "--limit=all"):
            with self.assertRaises(InvalidParam, msg=evil):
                await service.run("test:sleep", {"host": evil}, valid_names=NAMES, registry=REGISTRY)

    async def test_missing_and_unexpected_params_rejected(self):
        with self.assertRaises(InvalidParam):
            await service.run("test:sleep", {}, valid_names=NAMES, registry=REGISTRY)
        with self.assertRaises(InvalidParam):
            await service.run("test:echo", {"bogus": "web-01"}, valid_names=NAMES, registry=REGISTRY)


class InventoryFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_failure_is_a_clean_console_error(self):
        """With no injectable names, loading the real inventory must raise a
        ConsoleError (mapped to 503/exit-code), never a bare 500."""
        import os
        import tempfile

        from console.core.errors import ConsoleError

        with tempfile.TemporaryDirectory() as empty:
            old = os.environ.get("CONSOLE_TARGET_DIR")
            os.environ["CONSOLE_TARGET_DIR"] = empty
            try:
                with self.assertRaises(ConsoleError):
                    await service.run("test:sleep", {"host": "web-01"}, registry=REGISTRY)
            finally:
                if old is None:
                    del os.environ["CONSOLE_TARGET_DIR"]
                else:
                    os.environ["CONSOLE_TARGET_DIR"] = old


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_target_refused(self):
        job = await service.run("test:sleep", {"host": "web-01"}, valid_names=NAMES, registry=REGISTRY)
        try:
            with self.assertRaises(TargetBusy):
                await service.run("test:sleep", {"host": "web-01"}, valid_names=NAMES, registry=REGISTRY)
            # a different target is not blocked
            other = await service.run("test:sleep", {"host": "web-02"}, valid_names=NAMES, registry=REGISTRY)
            async for _ in other.stream():
                pass
        finally:
            async for _ in job.stream():
                pass

    async def test_stream_lines_and_exit_code(self):
        job = await service.run("test:echo", {}, valid_names=NAMES, registry=REGISTRY)
        lines = [line async for line in job.stream()]
        self.assertEqual(lines, ["line-a", "line-b"])
        self.assertEqual(job.exit_code, 0)
        self.assertEqual(job.status.value, "succeeded")


class DangerGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_destructive_requires_typed_confirmation(self):
        with self.assertRaises(ConfirmationRequired):
            await service.run("test:nuke", {"host": "web-01"}, valid_names=NAMES, registry=REGISTRY)
        with self.assertRaises(ConfirmationRequired):
            await service.run(
                "test:nuke", {"host": "web-01", "confirm": "wrong"}, valid_names=NAMES, registry=REGISTRY
            )
        job = await service.run(
            "test:nuke", {"host": "web-01", "confirm": "web-01"}, valid_names=NAMES, registry=REGISTRY
        )
        async for _ in job.stream():
            pass
        self.assertEqual(job.exit_code, 0)


class ImportIsolationTests(unittest.TestCase):
    def test_core_never_imports_interface_libs(self):
        """console.core must import cleanly with no FastAPI/uvicorn/argparse-wiring in sys.modules."""
        code = (
            "import console.core, sys; "
            "leaked = {m for m in ('fastapi', 'uvicorn', 'pydantic', 'starlette') if m in sys.modules}; "
            "assert not leaked, f'core leaked interface imports: {leaked}'"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
