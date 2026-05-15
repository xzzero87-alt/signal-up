"""RunnerHandle 단위 테스트 — M16 Phase 1 RED."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from signal_program.web.runner_handle import RunnerHandle, RunnerStateError


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


async def _sleeping_runner() -> None:
    await asyncio.sleep(100)


async def _fast_failing_runner() -> None:
    raise RuntimeError("runner crashed")


async def _stubborn_runner() -> None:
    try:
        await asyncio.sleep(100)
    except asyncio.CancelledError:
        await asyncio.sleep(1)
        raise


def _make_handle(factory=None, grace: float = 1.0) -> RunnerHandle:  # type: ignore[no-untyped-def]
    return RunnerHandle(
        runner_factory=factory or _sleeping_runner,
        stop_grace_sec=grace,
    )


# ── start / stop ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_start_when_stopped_succeeds() -> None:
    handle = _make_handle()
    await handle.start()
    try:
        assert handle.status().running is True
    finally:
        await handle.stop()


@pytest.mark.anyio
async def test_start_when_running_raises_state_error() -> None:
    handle = _make_handle()
    await handle.start()
    try:
        with pytest.raises(RunnerStateError):
            await handle.start()
    finally:
        await handle.stop()


@pytest.mark.anyio
async def test_stop_when_running_succeeds() -> None:
    handle = _make_handle()
    await handle.start()
    await handle.stop()
    assert handle.status().running is False


@pytest.mark.anyio
async def test_stop_when_stopped_raises_state_error() -> None:
    handle = _make_handle()
    with pytest.raises(RunnerStateError):
        await handle.stop()


# ── 상태 ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_status_reports_running_after_start() -> None:
    handle = _make_handle()
    assert handle.status().running is False
    await handle.start()
    try:
        assert handle.status().running is True
    finally:
        await handle.stop()


@pytest.mark.anyio
async def test_status_reports_started_at_in_kst() -> None:
    from zoneinfo import ZoneInfo

    kst = ZoneInfo("Asia/Seoul")
    handle = _make_handle()
    before = datetime.now(tz=kst)
    await handle.start()
    try:
        s = handle.status()
        assert s.started_at is not None
        assert s.started_at.tzinfo is not None
        assert s.started_at >= before
    finally:
        await handle.stop()


# ── supervisor ────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_runner_exception_does_not_propagate() -> None:
    handle = _make_handle(factory=_fast_failing_runner)
    await handle.start()
    await asyncio.sleep(0.1)
    assert handle.status().running is False


@pytest.mark.anyio
async def test_stop_force_cancels_after_grace() -> None:
    handle = _make_handle(factory=_stubborn_runner, grace=0.1)
    await handle.start()
    await asyncio.wait_for(handle.stop(), timeout=3.0)
    assert handle.status().running is False


# ── last_signal_at ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_last_signal_at_updates_when_runner_emits(tmp_path: Path) -> None:
    from signal_program.state.signal_history import SignalHistory

    history = SignalHistory(tmp_path / "signal_history.jsonl")
    history.append({"market": "KRW-BTC", "direction": "buy", "sent_at": "2025-01-01T10:00:00+09:00"})

    handle = RunnerHandle(runner_factory=_sleeping_runner, history=history)
    await handle.start()
    try:
        assert handle.status().last_signal_at is not None
    finally:
        await handle.stop()


@pytest.mark.anyio
async def test_last_signal_at_is_none_when_no_history() -> None:
    handle = _make_handle()
    assert handle.status().last_signal_at is None


# ── stop_if_running ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_stop_if_running_ignores_stopped_state() -> None:
    handle = _make_handle()
    await handle.stop_if_running()
    assert handle.status().running is False
