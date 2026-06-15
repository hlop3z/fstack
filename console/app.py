"""Interface adapter #2: HTTP -> core. Marshalling ONLY.

Tripwire (spec console-api): if this file ever branches on an action name,
logic has leaked out of the core. Routes marshal to core's actions + secrets
subsystems; the secrets save runs whatever derived renders core.secrets returns
(no name branching). Side-effecting routes: POST /api/run, POST /api/secrets.

Secrets are localhost-only by construction (`serve` binds 127.0.0.1) and the
plaintext is never persisted, cached (no-store), or logged.
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


class SaveSecrets(BaseModel):
    yaml: str


@app.get("/api/secrets")
async def secrets_open() -> JSONResponse:
    import yaml

    from .core import secrets as sec

    manifest = sec.load_manifest()
    data = sec.open_all(manifest)
    text = yaml.safe_dump(data, sort_keys=True, default_flow_style=False)
    return JSONResponse(
        {"yaml": text, "keys": sorted(data), "file": manifest.file.name},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/secrets")
async def secrets_save(body: SaveSecrets) -> JSONResponse:
    import yaml

    from .core import secrets as sec

    manifest = sec.load_manifest()
    new = yaml.safe_load(body.yaml)
    if not isinstance(new, dict):
        raise core.ConsoleError("secrets must be a YAML mapping of key: value")
    actions = sec.save_all(manifest, new)  # writes; returns the derived renders to run
    jobs = []
    for action in actions:  # run whatever core.secrets returns — no name branching
        job = await core.run(action, {})
        jobs.append({"action": action, "job_id": job.id})
    return JSONResponse(
        {"saved": True, "render_jobs": jobs}, headers={"Cache-Control": "no-store"}
    )


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
