"""RunnerService.on_signal_sent 배선 통합 테스트 (ADR-0020 Task 3)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from signal_program.config import Settings
from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import Candle, IndicatorSnapshot, Signal
from signal_program.runner import RunnerService
from signal_program.state.cooldown import CooldownStore
from signal_program.state.signal_log import SignalLog

KST = ZoneInfo("Asia/Seoul")
pytestmark = pytest.mark.anyio
NOW = datetime(2026, 6, 11, 10, 0, tzinfo=KST)


def _make_candles(n: int = 200) -> list[Candle]:
    return [
        Candle(
            market="KRW-BTC",
            opened_at=NOW - timedelta(hours=n - i),
            open=50_000_000.0,
            high=51_000_000.0,
            low=49_000_000.0,
            close=50_500_000.0,
            volume=1.0,
            quote_volume=50_500_000.0,
        )
        for i in range(n)
    ]


def _make_signal() -> Signal:
    return Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=50_000_000.0,
        triggered_at=NOW,
        indicators=IndicatorSnapshot(
            bb_upper=52_000_000.0,
            bb_middle=50_000_000.0,
            bb_lower=48_000_000.0,
            bb_width=0.04,
            bb_pct_b=0.5,
            cci=-150.0,
            volume_ratio=1.3,
        ),
    )


def _make_runner(tmp_path: Path, *, dry_run: bool, on_signal_sent=None) -> RunnerService:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        whitelist_markets=["KRW-BTC"],
        dry_run=dry_run,
        signals_log_path=tmp_path / "signals.jsonl",
        charts_dir=tmp_path / "charts",
    )
    return RunnerService(
        settings=settings,
        exchange=AsyncMock(**{"fetch_candles.return_value": _make_candles()}),
        strategy=MagicMock(evaluate=MagicMock(return_value=[_make_signal()])),
        cooldown=CooldownStore(path=tmp_path / "cd.json", cooldown=timedelta(hours=2)),
        notifier=AsyncMock(),
        signal_log=SignalLog(path=settings.signals_log_path),
        charts_dir=settings.charts_dir,
        on_signal_sent=on_signal_sent,
    )


@patch("signal_program.runner.generate_snapshot", return_value=None)
async def test_on_signal_sent_called_non_dry_run(_snap: MagicMock, tmp_path: Path) -> None:
    """non-dry_run 모드: 시그널 발송 후 on_signal_sent가 호출된다."""
    received: list[Signal] = []

    async def callback(signal: Signal) -> None:
        received.append(signal)

    runner = _make_runner(tmp_path, dry_run=False, on_signal_sent=callback)
    await runner.run_one_cycle(NOW, "t01")
    await asyncio.sleep(0)  # create_task가 실행될 기회를 줌

    assert len(received) == 1
    assert received[0].market == "KRW-BTC"


@patch("signal_program.runner.generate_snapshot", return_value=None)
async def test_on_signal_sent_not_called_dry_run(_snap: MagicMock, tmp_path: Path) -> None:
    """dry_run 모드: on_signal_sent가 호출되지 않는다."""
    received: list[Signal] = []

    async def callback(signal: Signal) -> None:
        received.append(signal)

    runner = _make_runner(tmp_path, dry_run=True, on_signal_sent=callback)
    await runner.run_one_cycle(NOW, "t02")
    await asyncio.sleep(0)

    assert received == []


@patch("signal_program.runner.generate_snapshot", return_value=None)
async def test_on_signal_sent_none_no_error(_snap: MagicMock, tmp_path: Path) -> None:
    """on_signal_sent=None(기본값): 기존 동작 그대로, 오류 없음."""
    runner = _make_runner(tmp_path, dry_run=False, on_signal_sent=None)
    report = await runner.run_one_cycle(NOW, "t03")
    assert report.signals_sent == 1


@patch("signal_program.runner.generate_snapshot", return_value=None)
async def test_on_signal_sent_exception_does_not_kill_cycle(
    _snap: MagicMock, tmp_path: Path
) -> None:
    """콜백이 예외를 던져도 사이클이 죽지 않는다 (create_task 격리)."""

    async def failing_callback(signal: Signal) -> None:
        raise ValueError("enrichment 오류 시뮬레이션")

    runner = _make_runner(tmp_path, dry_run=False, on_signal_sent=failing_callback)
    report = await runner.run_one_cycle(NOW, "t04")
    await asyncio.sleep(0)

    assert report.signals_sent == 1  # 사이클은 정상 완료
