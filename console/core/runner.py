"""Process spawning and line streaming. exec only — never a shell."""

import asyncio
import os
from collections.abc import AsyncIterator


async def spawn(argv: tuple[str, ...], cwd: str) -> asyncio.subprocess.Process:
    env = os.environ.copy()
    env.update(
        PYTHONUNBUFFERED="1",
        ANSIBLE_FORCE_COLOR="0",
        ANSIBLE_NOCOLOR="1",
    )
    return await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
    )


async def lines(proc: asyncio.subprocess.Process) -> AsyncIterator[str]:
    """Yield merged stdout+stderr lines as they are produced."""
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
    await proc.wait()
