"""데몬 제어 API — M13 stub, M16에서 실 구현."""

from __future__ import annotations

from fastapi import APIRouter

from signal_program.web.schemas import DaemonStatus

router = APIRouter(tags=["daemon"])


@router.get("/api/daemon/status", response_model=DaemonStatus)
def daemon_status() -> DaemonStatus:
    return DaemonStatus(running=False)


@router.post("/api/daemon/start", status_code=202)
def daemon_start() -> dict[str, str]:
    return {"message": "데몬 제어는 M16에서 활성화됩니다."}


@router.post("/api/daemon/stop", status_code=202)
def daemon_stop() -> dict[str, str]:
    return {"message": "데몬 제어는 M16에서 활성화됩니다."}
