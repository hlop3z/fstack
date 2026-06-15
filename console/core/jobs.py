"""In-memory job table. One running job per target; restart loses history by design."""

import asyncio
import itertools
from dataclasses import dataclass, field
from enum import Enum

from . import runner
from .errors import TargetBusy, UnknownJob


class JobStatus(Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self is not JobStatus.RUNNING


_ids = itertools.count(1)


@dataclass
class Job:
    id: str
    action: str
    target: str
    argv: tuple[str, ...]
    status: JobStatus = JobStatus.RUNNING
    exit_code: int | None = None
    lines: list[str] = field(default_factory=list)
    _changed: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def _append(self, line: str) -> None:
        self.lines.append(line)
        self._changed.set()
        self._changed = asyncio.Event()

    def _finish(self, exit_code: int) -> None:
        self.exit_code = exit_code
        self.status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
        self._changed.set()

    async def stream(self):
        """Yield all lines from the start, live until the job is terminal."""
        i = 0
        while True:
            while i < len(self.lines):
                yield self.lines[i]
                i += 1
            if self.status.terminal:
                return
            changed = self._changed
            if i >= len(self.lines) and not self.status.terminal:
                await changed.wait()

    def summary(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "target": self.target,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "line_count": len(self.lines),
        }


_jobs: dict[str, Job] = {}
_running_by_target: dict[str, str] = {}  # target -> job id


def get(job_id: str) -> Job:
    try:
        return _jobs[job_id]
    except KeyError:
        raise UnknownJob(f"no such job: {job_id}") from None


def all_jobs() -> list[Job]:
    return list(_jobs.values())


async def start(action_name: str, target: str, argv: tuple[str, ...], cwd: str) -> Job:
    running = _running_by_target.get(target)
    if running is not None and not _jobs[running].status.terminal:
        raise TargetBusy(f"target '{target}' already has running job {running}")

    job = Job(id=str(next(_ids)), action=action_name, target=target, argv=argv)
    _jobs[job.id] = job
    _running_by_target[target] = job.id

    async def pump() -> None:
        try:
            proc = await runner.spawn(argv, cwd=cwd)
        except OSError as exc:  # e.g. binary not found
            job._append(f"[console] failed to spawn {argv[0]}: {exc}")
            job._finish(127)
            return
        async for line in runner.lines(proc):
            job._append(line)
        job._finish(proc.returncode if proc.returncode is not None else 1)

    asyncio.get_running_loop().create_task(pump())
    return job
