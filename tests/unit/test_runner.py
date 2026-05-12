"""RunnerService — mock 기반 1사이클 테스트 8종."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path  # noqa: TC003
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from signal_program.config import Settings
from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import Candle, IndicatorSnapshot, Signal
from signal_program.runner import RunnerService
from signal_program.state.signal_log import SignalLog  # noqa: F401

KST = ZoneInfo("Asia/Seoul")
pytestmark = pytest.mark.anyio
NOW = datetime(2026, 5, 12, 14, 0, tzinfo=KST)


def make_settings(markets: list[str] | None = None, **kw: object) -> Settings:
    defaults: dict = {
        "whitelist_markets": markets or ["KRW-BTC"],
        "cycle_delay_seconds": 0,
        "dry_run": False,
    }
    defaults.update(kw)
    return Settings(**defaults)  # type: ignore[arg-type]


def make_candle(market: str = "KRW-BTC") -> Candle:
    return Candle(
        market=market,
        opened_at=NOW,
        open=50_000_000.0,
        high=51_000_000.0,
        low=49_000_000.0,
        close=50_500_000.0,
        volume=1.0,
        quote_volume=50_500_000.0,
    )


def make_signal(
    market: str = "KRW-BTC",
    mode: StrategyMode = StrategyMode.MEAN_REVERSION,
    direction: SignalDirection = SignalDirection.BUY,
) -> Signal:
    return Signal(
        market=market,
        timeframe=Timeframe.HOUR_1,
        mode=mode,
        direction=direction,
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


def make_runner(
    tmp_path: Path,
    settings: Settings | None = None,
    exchange: AsyncMock | None = None,
    strategy: MagicMock | None = None,
    cooldown: MagicMock | None = None,
    notifier: AsyncMock | None = None,
    signal_log: AsyncMock | None = None,
) -> RunnerService:
    return RunnerService(
        settings=settings or make_settings(),
        exchange=exchange or _default_exchange(),
        strategy=strategy or MagicMock(evaluate=MagicMock(return_value=[])),
        cooldown=cooldown or MagicMock(is_cooled_down=MagicMock(return_value=False)),
        notifier=notifier or AsyncMock(),
        signal_log=signal_log or AsyncMock(),
        charts_dir=tmp_path,
    )


def _default_exchange() -> AsyncMock:
    ex = AsyncMock()
    ex.fetch_candles.return_value = [make_candle()] * 200
    return ex


# ── 8 시나리오 ────────────────────────────────────────────────────────────────

@patch("signal_program.runner.generate_snapshot")
async def test_a_no_signal_no_notify(mock_snap: MagicMock, tmp_path: Path) -> None:
    notifier = AsyncMock()
    slog = AsyncMock()
    runner = make_runner(tmp_path, notifier=notifier, signal_log=slog,
                         strategy=MagicMock(evaluate=MagicMock(return_value=[])))
    report = await runner.run_one_cycle(NOW, "t001")
    notifier.send_signal.assert_not_called()
    slog.append.assert_not_called()
    assert report.signals_sent == 0


@patch("signal_program.runner.generate_snapshot")
async def test_b_signal_sends_and_marks(mock_snap: MagicMock, tmp_path: Path) -> None:
    sig = make_signal()
    mock_snap.return_value = tmp_path / "chart.png"
    notifier = AsyncMock()
    slog = AsyncMock()
    cooldown = MagicMock(is_cooled_down=MagicMock(return_value=False))
    runner = make_runner(tmp_path, notifier=notifier, signal_log=slog, cooldown=cooldown,
                         strategy=MagicMock(evaluate=MagicMock(return_value=[sig])))
    report = await runner.run_one_cycle(NOW, "t002")
    notifier.send_signal.assert_called_once()
    cooldown.mark_sent.assert_called_once()
    assert slog.append.call_args[0][1] == "ok"
    assert report.signals_sent == 1


@patch("signal_program.runner.generate_snapshot")
async def test_c_cooled_down_no_send(mock_snap: MagicMock, tmp_path: Path) -> None:
    sig = make_signal()
    notifier = AsyncMock()
    slog = AsyncMock()
    cooldown = MagicMock(is_cooled_down=MagicMock(return_value=True))
    runner = make_runner(tmp_path, notifier=notifier, signal_log=slog, cooldown=cooldown,
                         strategy=MagicMock(evaluate=MagicMock(return_value=[sig])))
    await runner.run_one_cycle(NOW, "t003")
    notifier.send_signal.assert_not_called()
    assert slog.append.call_args[0][1] == "cooled_down"


@patch("signal_program.runner.generate_snapshot")
async def test_d_two_signals_both_processed(mock_snap: MagicMock, tmp_path: Path) -> None:
    sigs = [make_signal(mode=StrategyMode.MEAN_REVERSION),
            make_signal(mode=StrategyMode.SQUEEZE_BREAKOUT)]
    mock_snap.return_value = tmp_path / "chart.png"
    notifier = AsyncMock()
    slog = AsyncMock()
    cooldown = MagicMock(is_cooled_down=MagicMock(return_value=False))
    runner = make_runner(tmp_path, notifier=notifier, signal_log=slog, cooldown=cooldown,
                         strategy=MagicMock(evaluate=MagicMock(return_value=sigs)))
    report = await runner.run_one_cycle(NOW, "t004")
    assert notifier.send_signal.call_count == 2
    assert cooldown.mark_sent.call_count == 2
    assert report.signals_sent == 2


@patch("signal_program.runner.generate_snapshot")
async def test_e_fetch_exception_skips_market(mock_snap: MagicMock, tmp_path: Path) -> None:
    settings = make_settings(markets=["KRW-BTC", "KRW-ETH"])
    exchange = AsyncMock()
    exchange.fetch_candles.side_effect = [
        RuntimeError("API down"),
        [make_candle("KRW-ETH")] * 200,
    ]
    runner = make_runner(tmp_path, settings=settings, exchange=exchange,
                         strategy=MagicMock(evaluate=MagicMock(return_value=[])))
    report = await runner.run_one_cycle(NOW, "t005")
    assert len(report.failures) == 1
    assert "KRW-BTC" in report.failures[0]


@patch("signal_program.runner.generate_snapshot")
async def test_f_chart_exception_notifier_gets_none(mock_snap: MagicMock, tmp_path: Path) -> None:
    sig = make_signal()
    mock_snap.side_effect = RuntimeError("matplotlib error")
    notifier = AsyncMock()
    cooldown = MagicMock(is_cooled_down=MagicMock(return_value=False))
    runner = make_runner(tmp_path, notifier=notifier, cooldown=cooldown,
                         strategy=MagicMock(evaluate=MagicMock(return_value=[sig])))
    await runner.run_one_cycle(NOW, "t006")
    notifier.send_signal.assert_called_once()
    assert notifier.send_signal.call_args[0][1] is None


@patch("signal_program.runner.generate_snapshot")
async def test_g_dry_run_no_mark_sent(mock_snap: MagicMock, tmp_path: Path) -> None:
    sig = make_signal()
    mock_snap.return_value = tmp_path / "chart.png"
    settings = make_settings(dry_run=True)
    cooldown = MagicMock(is_cooled_down=MagicMock(return_value=False))
    slog = AsyncMock()
    runner = make_runner(tmp_path, settings=settings, cooldown=cooldown, signal_log=slog,
                         strategy=MagicMock(evaluate=MagicMock(return_value=[sig])))
    await runner.run_one_cycle(NOW, "t007")
    cooldown.mark_sent.assert_not_called()
    assert slog.append.call_args[0][1] == "dry_run"


@patch("signal_program.runner.generate_snapshot")
async def test_h_semaphore_limits_concurrency(mock_snap: MagicMock, tmp_path: Path) -> None:
    settings = make_settings(markets=[f"KRW-COIN{i}" for i in range(8)])
    current = [0]
    peak = [0]

    exchange = AsyncMock()

    async def slow_fetch(*a: object, **kw: object) -> list:
        current[0] += 1
        peak[0] = max(peak[0], current[0])
        await asyncio.sleep(0.03)
        current[0] -= 1
        return []

    exchange.fetch_candles.side_effect = slow_fetch
    runner = make_runner(tmp_path, settings=settings, exchange=exchange,
                         strategy=MagicMock(evaluate=MagicMock(return_value=[])))
    await runner.run_one_cycle(NOW, "t008")
    assert peak[0] <= 5
