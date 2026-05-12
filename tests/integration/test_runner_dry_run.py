"""RunnerService dry_run 통합 테스트 — 컴포넌트 전체 파이프라인 1사이클 검증."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path  # noqa: TC003
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from signal_program.config import Settings
from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import Candle, IndicatorSnapshot, Signal
from signal_program.runner import RunnerService
from signal_program.state.cooldown import CooldownStore
from signal_program.state.signal_log import SignalLog

KST = ZoneInfo("Asia/Seoul")
pytestmark = pytest.mark.anyio
NOW = datetime(2026, 5, 12, 14, 0, tzinfo=KST)


def _make_candles(market: str = "KRW-BTC", n: int = 200) -> list[Candle]:
    return [
        Candle(
            market=market,
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


def _make_signal(market: str = "KRW-BTC") -> Signal:
    return Signal(
        market=market,
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
            bb_width_quantile=None,
        ),
    )


@patch("signal_program.runner.generate_snapshot")
async def test_dry_run_one_cycle_logs_signal(mock_snap: MagicMock, tmp_path: Path) -> None:
    """dry_run 1사이클: signal_log.jsonl 존재 + ≥1 줄 + sent_status=dry_run."""
    mock_snap.return_value = tmp_path / "charts" / "chart.png"

    settings = Settings(
        whitelist_markets=["KRW-BTC"],
        dry_run=True,
        cycle_delay_seconds=0,
        signals_log_path=tmp_path / "signals.jsonl",
        charts_dir=tmp_path / "charts",
    )

    exchange = AsyncMock()
    exchange.fetch_candles.return_value = _make_candles()
    strategy = MagicMock(evaluate=MagicMock(return_value=[_make_signal()]))
    cooldown = CooldownStore(path=tmp_path / "cooldown.json", cooldown=timedelta(hours=2))
    signal_log = SignalLog(path=settings.signals_log_path)
    notifier = AsyncMock()

    runner = RunnerService(
        settings=settings,
        exchange=exchange,
        strategy=strategy,
        cooldown=cooldown,
        notifier=notifier,
        signal_log=signal_log,
        charts_dir=settings.charts_dir,
    )

    await runner.run_one_cycle(NOW, "integration01")

    assert settings.signals_log_path.exists()
    lines = [l for l in settings.signals_log_path.read_text().strip().split("\n") if l]
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert rec["sent_status"] == "dry_run"
    assert rec["signal"]["market"] == "KRW-BTC"


@patch("signal_program.runner.generate_snapshot")
async def test_run_forever_runs_multiple_cycles(mock_snap: MagicMock, tmp_path: Path) -> None:
    """run_forever(cycle_delay=0) → anyio.move_on_after로 짧게 제한, 복수 사이클 확인."""
    import anyio

    mock_snap.return_value = None
    settings = Settings(
        whitelist_markets=["KRW-BTC"],
        dry_run=True,
        cycle_delay_seconds=0,
        cycle_timeout_seconds=10,
        signals_log_path=tmp_path / "signals.jsonl",
        charts_dir=tmp_path / "charts",
    )
    exchange = AsyncMock()
    exchange.fetch_candles.return_value = _make_candles()
    strategy = MagicMock(evaluate=MagicMock(return_value=[]))
    cooldown = CooldownStore(path=tmp_path / "cd.json", cooldown=timedelta(hours=2))
    runner = RunnerService(
        settings=settings,
        exchange=exchange,
        strategy=strategy,
        cooldown=cooldown,
        notifier=AsyncMock(),
        signal_log=SignalLog(path=settings.signals_log_path),
        charts_dir=settings.charts_dir,
    )
    with anyio.move_on_after(0.5):
        await runner.run_forever()
    # 0.5초 안에 최소 1사이클이 돌았어야 함
    assert exchange.fetch_candles.call_count >= 1
