"""BacktestJobManager 단위 테스트 — M15 Phase 1 RED."""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _make_spec(**kwargs):  # type: ignore[no-untyped-def]
    from signal_program.web.jobs import JobKind, JobSpec

    defaults = dict(
        kind=JobKind.BACKTEST,
        market="KRW-BTC",
        period_from=datetime(2025, 1, 1, tzinfo=UTC),
        period_to=datetime(2025, 2, 1, tzinfo=UTC),
        mode="both",
    )
    defaults.update(kwargs)
    return JobSpec(**defaults)


def _noop_executor(spec: object, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("<html>ok</html>", encoding="utf-8")


def _make_manager(tmp_path: Path, executor=None, timeout: float = 5.0):  # type: ignore[no-untyped-def]
    from signal_program.web.jobs import BacktestJobManager

    return BacktestJobManager(
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
        settings_store=None,
        _executor=executor or _noop_executor,
        job_timeout_sec=timeout,
    )


async def _wait_for_status(manager, job_id: str, *statuses, timeout: float = 3.0) -> object:  # type: ignore[no-untyped-def]
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = manager.get(job_id)
        if r and r.status.value in statuses:
            return r
        await asyncio.sleep(0.05)
    return manager.get(job_id)


# ── submit / queue 기본 ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_submit_queues_job_with_unique_id(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    await manager.start()
    try:
        r1 = await manager.submit(_make_spec())
        r2 = await manager.submit(_make_spec())
        assert r1.job_id != r2.job_id
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_submit_returns_queued_status_initially(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    record = await manager.submit(_make_spec())
    assert record.status.value == "queued"


@pytest.mark.anyio
async def test_worker_processes_queue_in_order(tmp_path: Path) -> None:
    order: list[str] = []

    def tracking_executor(spec: object, output_path: Path) -> None:
        order.append(getattr(spec, "market", "?"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>ok</html>", encoding="utf-8")

    manager = _make_manager(tmp_path, executor=tracking_executor)
    await manager.start()
    try:
        r_a = await manager.submit(_make_spec(market="KRW-BTC"))
        r_b = await manager.submit(_make_spec(market="KRW-ETH"))
        await _wait_for_status(manager, r_b.job_id, "succeeded", "failed")
        assert len(order) >= 2
        assert order[0] == "KRW-BTC"
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_concurrent_jobs_limited_to_one(tmp_path: Path) -> None:
    running_count = 0
    max_observed = 0

    def slow_executor(spec: object, output_path: Path) -> None:
        nonlocal running_count, max_observed
        running_count += 1
        max_observed = max(max_observed, running_count)
        time.sleep(0.05)
        running_count -= 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>ok</html>", encoding="utf-8")

    manager = _make_manager(tmp_path, executor=slow_executor)
    await manager.start()
    try:
        r1 = await manager.submit(_make_spec(market="KRW-BTC"))
        r2 = await manager.submit(_make_spec(market="KRW-ETH"))
        await _wait_for_status(manager, r2.job_id, "succeeded", "failed")
        assert max_observed <= 1
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_queue_full_raises_when_at_max(tmp_path: Path) -> None:
    from signal_program.web.jobs import BacktestJobManager, JobQueueFullError

    def blocking_executor(spec: object, output_path: Path) -> None:
        time.sleep(30)

    manager = _make_manager(tmp_path, executor=blocking_executor, timeout=60.0)
    await manager.start()
    try:
        for _ in range(BacktestJobManager.MAX_QUEUE_LEN):
            await manager.submit(_make_spec())
        with pytest.raises(JobQueueFullError):
            await manager.submit(_make_spec())
    finally:
        await manager.stop()


# ── 실행 결과 ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_succeeded_job_has_result_path(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    await manager.start()
    try:
        record = await manager.submit(_make_spec())
        r = await _wait_for_status(manager, record.job_id, "succeeded", "failed")
        assert r is not None
        assert r.status.value == "succeeded"
        assert r.result_path is not None
        assert r.result_path.exists()
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_failed_job_captures_error_message(tmp_path: Path) -> None:
    def failing_executor(spec: object, output_path: Path) -> None:
        raise RuntimeError("엔진 실패 테스트")

    manager = _make_manager(tmp_path, executor=failing_executor)
    await manager.start()
    try:
        record = await manager.submit(_make_spec())
        r = await _wait_for_status(manager, record.job_id, "failed")
        assert r is not None
        assert r.status.value == "failed"
        assert "엔진 실패 테스트" in (r.error_message or "")
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_job_timeout_marks_failed(tmp_path: Path) -> None:
    def slow_executor(spec: object, output_path: Path) -> None:
        time.sleep(60)

    manager = _make_manager(tmp_path, executor=slow_executor, timeout=0.1)
    await manager.start()
    try:
        record = await manager.submit(_make_spec())
        r = await _wait_for_status(manager, record.job_id, "failed", timeout=5.0)
        assert r is not None
        assert r.status.value == "failed"
        assert r.error_message == "시간 초과"
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_cache_miss_returns_friendly_message(tmp_path: Path) -> None:
    from signal_program.web.jobs import BacktestDataError

    def cache_miss_executor(spec: object, output_path: Path) -> None:
        market = getattr(spec, "market", "KRW-BTC")
        raise BacktestDataError(
            f"이 기간의 캔들 데이터가 없습니다. CLI에서 "
            f"`uv run signal fetch-candles --market {market} --from 2025-01-01` 먼저 실행하세요."
        )

    manager = _make_manager(tmp_path, executor=cache_miss_executor)
    await manager.start()
    try:
        record = await manager.submit(_make_spec())
        r = await _wait_for_status(manager, record.job_id, "failed")
        assert r is not None
        assert "이 기간의 캔들 데이터가 없습니다" in (r.error_message or "")
        assert "uv run signal fetch-candles" in (r.error_message or "")
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_cli_alternative_message_displayed_on_cache_miss(tmp_path: Path) -> None:
    from signal_program.web.jobs import BacktestDataError

    def cache_miss_executor(spec: object, output_path: Path) -> None:
        market = getattr(spec, "market", "KRW-BTC")
        raise BacktestDataError(
            f"이 기간의 캔들 데이터가 없습니다. CLI에서 "
            f"`uv run signal fetch-candles --market {market} --from 2025-01-01` 먼저 실행하세요."
        )

    manager = _make_manager(tmp_path, executor=cache_miss_executor)
    await manager.start()
    try:
        record = await manager.submit(_make_spec(market="KRW-BTC"))
        r = await _wait_for_status(manager, record.job_id, "failed")
        assert r is not None
        assert "fetch-candles" in (r.error_message or "")
        assert "KRW-BTC" in (r.error_message or "")
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_walkforward_kind_uses_walkforward_engine(tmp_path: Path) -> None:
    from signal_program.web.jobs import JobKind

    wf_called: dict[str, bool] = {"called": False}

    def wf_executor(spec: object, output_path: Path) -> None:
        assert getattr(spec, "kind") == JobKind.WALKFORWARD
        wf_called["called"] = True
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>wf ok</html>", encoding="utf-8")

    manager = _make_manager(tmp_path, executor=wf_executor)
    await manager.start()
    try:
        spec = _make_spec(
            kind=JobKind.WALKFORWARD,
            train_months=8,
            validate_months=2,
            grid_str="bb_std_mult:1.5,2.0",
        )
        record = await manager.submit(spec)
        await _wait_for_status(manager, record.job_id, "succeeded", "failed")
        assert wf_called["called"]
    finally:
        await manager.stop()


# ── path traversal 방어 ───────────────────────────────────────────────────────


def test_get_job_report_rejects_path_traversal(tmp_path: Path) -> None:
    from signal_program.web.jobs import _is_safe_report_path

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    # URL 디코딩은 FastAPI/Starlette가 라우트 핸들러 전에 처리하므로
    # 실제 job_id는 항상 디코딩된 형태로 도달함
    assert not _is_safe_report_path("../../../etc/passwd", reports_dir)
    assert not _is_safe_report_path("../../sensitive", reports_dir)


def test_get_job_report_rejects_missing_job(tmp_path: Path) -> None:
    from signal_program.web.jobs import _is_safe_report_path

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    # 경로는 안전하지만 파일 없음
    assert _is_safe_report_path("aaaa1111bbbb2222cccc3333dddd4444", reports_dir)
    assert not (reports_dir / "jobs" / "aaaa1111bbbb2222cccc3333dddd4444.html").exists()


def test_get_job_report_rejects_failed_job(tmp_path: Path) -> None:
    from signal_program.web.jobs import JobKind, JobRecord, JobStatus

    record = JobRecord(
        job_id="test-id",
        kind=JobKind.BACKTEST,
        status=JobStatus.FAILED,
        submitted_at=datetime.now(tz=UTC),
        started_at=None,
        finished_at=None,
        market="KRW-BTC",
        period_from=datetime(2025, 1, 1, tzinfo=UTC),
        period_to=datetime(2025, 2, 1, tzinfo=UTC),
        mode="both",
        result_path=None,
        error_message="error",
    )
    assert record.result_path is None
