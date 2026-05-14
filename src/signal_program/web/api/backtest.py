"""백테스트 잡 API — M13 stub, M15에서 실 구현."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from signal_program.web.schemas import JobView

router = APIRouter(tags=["backtest"])

_jobs: dict[str, JobView] = {}


class BacktestRunRequest(BaseModel):
    market: str
    period_from: str
    period_to: str
    modes: list[str]
    overrides: dict[str, float | int] = {}


@router.get("/api/backtest/jobs")
def list_jobs() -> list[JobView]:
    return list(_jobs.values())


@router.post("/api/backtest/jobs", status_code=202)
def create_job(body: BacktestRunRequest) -> dict[str, str]:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobView(
        job_id=job_id,
        status="queued",
        submitted_at=datetime.now(tz=UTC),
        market=body.market,
        period_from=body.period_from,
        period_to=body.period_to,
    )
    return {"job_id": job_id}


@router.get("/api/backtest/jobs/{job_id}")
def get_job(job_id: str) -> JobView:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]
