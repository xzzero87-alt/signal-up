"""백테스트 잡 API — M15 실 구현.

POST /api/backtest/jobs  → 202 JobView | 429
GET  /api/backtest/jobs  → list[JobView]
GET  /api/backtest/jobs/{job_id}  → JobView | 404
GET  /api/backtest/jobs/{job_id}/report  → HTML FileResponse | 404
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from signal_program.web.jobs import (  # noqa: TC001
    BacktestJobManager,
    JobKind,
    JobQueueFullError,
    JobRecord,
    JobSpec,
    _is_safe_report_path,
)
from signal_program.web.schemas import BacktestJobSubmit, JobView

router = APIRouter(tags=["backtest"])

_KST = ZoneInfo("Asia/Seoul")


def _get_manager(request: Request) -> BacktestJobManager:
    return request.app.state.job_manager  # type: ignore[no-any-return]


def _to_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=_KST)


def _record_to_view(r: JobRecord) -> JobView:
    return JobView(
        job_id=r.job_id,
        kind=r.kind.value,
        status=r.status.value,
        submitted_at=r.submitted_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
        market=r.market,
        period_from=r.period_from.date().isoformat(),
        period_to=r.period_to.date().isoformat(),
        result_path=str(r.result_path) if r.result_path else None,
        error_message=r.error_message,
    )


@router.get("/api/backtest/jobs")
def list_jobs(
    limit: int = 20,
    manager: BacktestJobManager = Depends(_get_manager),
) -> list[JobView]:
    return [_record_to_view(r) for r in manager.list_recent(limit=limit)]


@router.post("/api/backtest/jobs", status_code=202)
async def submit_job(
    body: BacktestJobSubmit,
    manager: BacktestJobManager = Depends(_get_manager),
) -> JobView:
    spec = JobSpec(
        kind=JobKind(body.kind),
        market=body.market,
        period_from=_to_dt(body.period_from),
        period_to=_to_dt(body.period_to),
        mode=body.mode,
        train_months=body.train_months,
        validate_months=body.validate_months,
        grid_str=body.grid_str,
    )
    try:
        record = await manager.submit(spec)
    except JobQueueFullError as exc:
        msg = (
            f"잡 큐가 가득 찼습니다 (최대 {manager.MAX_QUEUE_LEN}건)."
            " 진행 중인 작업이 끝날 때까지 기다리세요."
        )
        raise HTTPException(status_code=429, detail={"message": msg}) from exc
    return _record_to_view(record)


@router.get("/api/backtest/jobs/{job_id}")
def get_job(
    job_id: str,
    manager: BacktestJobManager = Depends(_get_manager),
) -> JobView:
    record = manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _record_to_view(record)


@router.get("/api/backtest/jobs/{job_id}/report", response_class=FileResponse)
def get_job_report(
    job_id: str,
    manager: BacktestJobManager = Depends(_get_manager),
) -> FileResponse:
    record = manager.get(job_id)
    if record is None or record.result_path is None:
        raise HTTPException(status_code=404, detail="Report not available")

    if not _is_safe_report_path(job_id, manager.reports_dir):
        raise HTTPException(status_code=404, detail="Invalid job id")

    safe_path = (manager.reports_dir / "jobs" / f"{job_id}.html").resolve()
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    return FileResponse(path=str(safe_path), media_type="text/html")
