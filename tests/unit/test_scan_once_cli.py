"""scan-once CLI 단위 테스트 (M9).

TDD RED → GREEN:
  - 시그널 없음 → exit 0, "시그널 없음" 메시지
  - 시그널 있음 → exit 0, 방향/강도 출력
  - 잘못된 전략 버전 → exit 1
  - 캔들 조회 실패 → exit 1
  - 캔들 빈 응답 → exit 1
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from signal_program.cli import app
from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import Candle, IndicatorSnapshot, Signal

_runner = CliRunner()
_KST = ZoneInfo("Asia/Seoul")

# ── 픽스처 ──────────────────────────────────────────────────────────────────


def _make_candles(n: int = 5) -> list[Candle]:
    now = datetime(2026, 5, 22, 9, 0, tzinfo=_KST)
    return [
        Candle(
            market="KRW-BTC",
            opened_at=now,
            open=100_000_000.0,
            high=101_000_000.0,
            low=99_000_000.0,
            close=100_500_000.0,
            volume=10.0,
            quote_volume=1_005_000_000.0,
        )
        for _ in range(n)
    ]


def _make_signal() -> Signal:
    return Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=100_500_000.0,
        triggered_at=datetime(2026, 5, 22, 9, 0, tzinfo=_KST),
        indicators=IndicatorSnapshot(
            bb_upper=102_000_000.0,
            bb_middle=100_000_000.0,
            bb_lower=98_000_000.0,
            bb_width=4_000_000.0,
            bb_pct_b=0.25,
            cci=-110.0,
            volume_ratio=1.5,
        ),
    )


# ── 공통 패치 헬퍼 ────────────────────────────────────────────────────────────


def _run_scan(
    market: str = "KRW-BTC",
    strategy_ver: str = "v1",
    candles: list[Candle] | None = None,
    signals: list[Signal] | None = None,
    fetch_raises: Exception | None = None,
) -> object:
    """scan-once 호출 공통 헬퍼.

    UpbitClient.fetch_candles와 strategy.evaluate를 모두 패치한 뒤
    typer CliRunner로 실행한 Result를 반환한다.
    """
    if candles is None:
        candles = _make_candles()
    if signals is None:
        signals = []

    mock_strategy = MagicMock()
    mock_strategy.evaluate.return_value = signals

    if fetch_raises is not None:
        mock_fetch = AsyncMock(side_effect=fetch_raises)
    else:
        mock_fetch = AsyncMock(return_value=candles)

    with (
        patch("signal_program.cli._make_exchange_client") as mock_exc_cls,
        patch("signal_program.cli._make_strategy") as mock_strat_fn,
    ):
        mock_client = MagicMock()
        mock_client.fetch_candles = mock_fetch
        mock_exc_cls.return_value = mock_client
        mock_strat_fn.return_value = mock_strategy

        return _runner.invoke(
            app,
            ["scan-once", "--market", market, "--strategy", strategy_ver],
            catch_exceptions=False,
        )


# ── 정상 케이스 ───────────────────────────────────────────────────────────────


class TestScanOnceNoSignal:
    def test_exit_0_when_no_signal(self) -> None:
        result = _run_scan(signals=[])
        assert result.exit_code == 0, result.output

    def test_output_contains_no_signal_message(self) -> None:
        result = _run_scan(signals=[])
        assert "시그널 없음" in result.output

    def test_output_contains_market_name(self) -> None:
        result = _run_scan(signals=[])
        assert "KRW-BTC" in result.output


class TestScanOnceWithSignal:
    def test_exit_0_when_signal_found(self) -> None:
        result = _run_scan(signals=[_make_signal()])
        assert result.exit_code == 0, result.output

    def test_output_contains_direction(self) -> None:
        result = _run_scan(signals=[_make_signal()])
        assert "buy" in result.output.lower()

    def test_output_contains_strength(self) -> None:
        result = _run_scan(signals=[_make_signal()])
        assert "normal" in result.output.lower()

    def test_output_contains_price(self) -> None:
        result = _run_scan(signals=[_make_signal()])
        assert "100" in result.output  # 100,500,000 포함


# ── 오류 케이스 ───────────────────────────────────────────────────────────────


class TestScanOnceErrors:
    def test_invalid_strategy_exits_1(self) -> None:
        result = _runner.invoke(
            app,
            ["scan-once", "--market", "KRW-BTC", "--strategy", "v99"],
            catch_exceptions=False,
        )
        assert result.exit_code == 1

    def test_fetch_failure_exits_1(self) -> None:
        result = _run_scan(fetch_raises=RuntimeError("API 오류"))
        assert result.exit_code == 1

    def test_empty_candles_exits_1(self) -> None:
        result = _run_scan(candles=[])
        assert result.exit_code == 1

    def test_fetch_failure_prints_error_message(self) -> None:
        result = _run_scan(fetch_raises=RuntimeError("API 오류"))
        assert result.exit_code == 1
