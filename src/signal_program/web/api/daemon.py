"""데몬 제어 API — M16 실 구현.

POST /api/daemon/start → 202 | 409
POST /api/daemon/stop  → 202 | 409
GET  /api/daemon/status → DaemonStatus
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from signal_program.web.runner_handle import RunnerHandle, RunnerStateError  # noqa: TC001
from signal_program.web.schemas import DaemonStatus

router = APIRouter(tags=["daemon"])


def _get_handle(request: Request) -> RunnerHandle:
    return request.app.state.runner_handle  # type: ignore[no-any-return]


@router.get("/api/daemon/status", response_model=DaemonStatus)
def daemon_status(handle: RunnerHandle = Depends(_get_handle)) -> DaemonStatus:
    s = handle.status()
    return DaemonStatus(
        running=s.running,
        started_at=s.started_at,
        last_signal_at=s.last_signal_at,
        next_poll_at=s.next_poll_at,
    )


@router.post("/api/daemon/start", status_code=202)
async def daemon_start(handle: RunnerHandle = Depends(_get_handle)) -> dict[str, str]:
    try:
        await handle.start()
    except RunnerStateError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
    return {"message": "데몬을 시작했습니다"}


@router.post("/api/daemon/stop", status_code=202)
async def daemon_stop(handle: RunnerHandle = Depends(_get_handle)) -> dict[str, str]:
    try:
        await handle.stop()
    except RunnerStateError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
    return {"message": "데몬을 정지했습니다"}
