"""Interface adapter #2: HTTP -> core. Marshalling ONLY.

Tripwire (spec console-api): if this file ever branches on an action name,
logic has leaked out of the core. Three API routes; POST /api/run is the only
one with side effects.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import core

app = FastAPI(title="infra-console", docs_url=None, redoc_url=None)

_STATUS = {
    core.UnknownAction: 400,
    core.InvalidParam: 400,
    core.ConfirmationRequired: 400,
    core.TargetBusy: 409,
    core.UnknownJob: 404,
    core.InventoryUnavailable: 503,
}


@app.exception_handler(core.ConsoleError)
async def _console_error(_, exc: core.ConsoleError) -> JSONResponse:
    return JSONResponse(status_code=_STATUS.get(type(exc), 500), content={"error": str(exc)})


class RunCommand(BaseModel):
    action: str
    params: dict[str, str] = {}


@app.post("/api/run")
async def run(cmd: RunCommand) -> dict:
    job = await core.run(cmd.action, cmd.params)
    return {"job_id": job.id}


@app.get("/api/state")
async def state() -> dict:
    return core.snapshot()


@app.get("/api/jobs/{job_id}/logs")
async def logs(job_id: str) -> StreamingResponse:
    job = core.get_job(job_id)  # raises UnknownJob -> 404 before streaming starts

    async def stream():
        async for line in job.stream():
            yield f"data: {line}\n\n"
        yield f"event: done\ndata: {job.status.value} exit={job.exit_code}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
