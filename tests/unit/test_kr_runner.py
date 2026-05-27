"""KrStockRunnerService 유닛 테스트.

네트워크 없이 실행 가능한 테스트만 포함한다.
- _is_market_open: 순수 함수 — 다양한 시각/요일 경계값 검증
- _next_hour_top: 순수 함수 — 정각 계산 검증
- KrCycleReport: Pydantic frozen 모델 검증
- run_one_cycle: exchange/strategy/notifier mock, cooldown 동작
- run_forever: market-open guard, HOUR_1/HOUR_2 선택 로직
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.kr_runner import (
    KrCycleReport,
    KrStockRunnerService,
    _is_market_open,
    _next_hour_top,
)
from signal_program.models import Candle, IndicatorSnapshot, Signal

KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------ #
# 헬퍼 픽스처
# ------------------------------------------------------------------ #


def _kst(year: int, month: int, day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=KST)


def _make_candle(symbol: str, dt: datetime) -> Candle:
    return Candle(
        market=symbol,
        opened_at=dt.astimezone(UTC),
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=1000.0,
        quote_volume=10_500_000.0,
    )


def _make_signal(
    symbol: str, timeframe: Timeframe = Timeframe.HOUR_1
) -> Signal:
    return Signal(
        market=symbol,
        timeframe=timeframe,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=105.0,
        triggered_at=datetime(2025, 5, 12, 10, 0, tzinfo=KST),
        indicators=IndicatorSnapshot(
            bb_upper=110.0,
            bb_middle=100.0,
            bb_lower=90.0,
            bb_width=0.2,
            bb_pct_b=0.5,
            cci=50.0,
            volume_ratio=1.2,
            bb_width_quantile=None,
        ),
    )


def _make_settings(**overrides: object) -> MagicMock:
    s = MagicMock()
    s.kr_whitelist_symbols = ["005930", "000660"]
    s.cycle_delay_seconds = 0
    s.cycle_timeout_seconds = 300
    s.kr_cooldown_hours_60m = 1
    s.kr_cooldown_hours_120m = 2
    s.charts_dir = Path("/tmp/charts")
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_runner(
    exchange: MagicMock | None = None,
    strategy: MagicMock | None = None,
    notifier: MagicMock | None = None,
    cooldown_60m: MagicMock | None = None,
    cooldown_120m: MagicMock | None = None,
    settings: MagicMock | None = None,
) -> KrStockRunnerService:
    if exchange is None:
        exchange = AsyncMock()
        exchange.list_symbols = AsyncMock(return_value=["005930"])
        exchange.fetch_candles = AsyncMock(return_value=[])
    if strategy is None:
        strategy = MagicMock()
        strategy.evaluate = MagicMock(return_value=[])
    if notifier is None:
        notifier = AsyncMock()
        notifier.send_signal = AsyncMock(return_value=None)
    if cooldown_60m is None:
        cooldown_60m = MagicMock()
        cooldown_60m.is_cooled_down = MagicMock(return_value=True)
        cooldown_60m.mark_sent = MagicMock()
    if cooldown_120m is None:
        cooldown_120m = MagicMock()
        cooldown_120m.is_cooled_down = MagicMock(return_value=True)
        cooldown_120m.mark_sent = MagicMock()
    if settings is None:
        settings = _make_settings()

    signal_log = MagicMock()
    signal_log.append = MagicMock()

    return KrStockRunnerService(
        settings=settings,
        exchange=exchange,
        strategy=strategy,
        notifier=notifier,
        signal_log=signal_log,
        cooldown_60m=cooldown_60m,
        cooldown_120m=cooldown_120m,
        charts_dir=Path("/tmp/charts"),
    )


# ------------------------------------------------------------------ #
# _is_market_open 순수 함수 테스트
# ------------------------------------------------------------------ #


class TestIsMarketOpen:
    def test_weekday_morning_before_open(self) -> None:
        """평일 09:00 이전은 미개장."""
        now = _kst(2025, 5, 12, 8, 59)  # Monday 08:59 KST
        assert _is_market_open(now) is False

    def test_weekday_at_open(self) -> None:
        """평일 09:00 정각은 개장."""
        now = _kst(2025, 5, 12, 9, 0)
        assert _is_market_open(now) is True

    def test_weekday_midday(self) -> None:
        """평일 점심시간(12:00)은 개장."""
        now = _kst(2025, 5, 12, 12, 0)
        assert _is_market_open(now) is True

    def test_weekday_just_before_close(self) -> None:
        """평일 15:29는 개장."""
        now = _kst(2025, 5, 12, 15, 29)
        assert _is_market_open(now) is True

    def test_weekday_at_close(self) -> None:
        """평일 15:30 정각은 폐장(미포함)."""
        now = _kst(2025, 5, 12, 15, 30)
        assert _is_market_open(now) is False

    def test_weekday_evening(self) -> None:
        """평일 18:00는 폐장."""
        now = _kst(2025, 5, 12, 18, 0)
        assert _is_market_open(now) is False

    def test_saturday(self) -> None:
        """토요일은 폐장."""
        now = _kst(2025, 5, 10, 11, 0)  # Saturday
        assert _is_market_open(now) is False

    def test_sunday(self) -> None:
        """일요일은 폐장."""
        now = _kst(2025, 5, 11, 11, 0)  # Sunday
        assert _is_market_open(now) is False

    def test_friday_open(self) -> None:
        """금요일 10:00은 개장."""
        now = _kst(2025, 5, 9, 10, 0)  # Friday
        assert _is_market_open(now) is True

    def test_utc_input_normalized_to_kst(self) -> None:
        """UTC datetime도 KST로 변환해서 판단한다."""
        # 2025-05-12 00:01 UTC = 2025-05-12 09:01 KST (Monday)
        now = datetime(2025, 5, 12, 0, 1, tzinfo=UTC)
        assert _is_market_open(now) is True


# ------------------------------------------------------------------ #
# _next_hour_top 순수 함수 테스트
# ------------------------------------------------------------------ #


class TestNextHourTop:
    def test_mid_hour(self) -> None:
        """30분 중간 → 다음 정각."""
        dt = _kst(2025, 5, 12, 10, 30)
        result = _next_hour_top(dt)
        assert result == _kst(2025, 5, 12, 11, 0)

    def test_exactly_at_hour(self) -> None:
        """정각 입력 → 한 시간 뒤 정각."""
        dt = _kst(2025, 5, 12, 10, 0)
        result = _next_hour_top(dt)
        assert result == _kst(2025, 5, 12, 11, 0)

    def test_one_second_past_hour(self) -> None:
        """정각 1초 지남 → 한 시간 뒤 정각."""
        dt = datetime(2025, 5, 12, 10, 0, 1, tzinfo=KST)
        result = _next_hour_top(dt)
        assert result == _kst(2025, 5, 12, 11, 0)

    def test_day_rollover(self) -> None:
        """23:30 → 다음 날 00:00."""
        dt = _kst(2025, 5, 12, 23, 30)
        result = _next_hour_top(dt)
        assert result == _kst(2025, 5, 13, 0, 0)


# ------------------------------------------------------------------ #
# KrCycleReport 모델 테스트
# ------------------------------------------------------------------ #


class TestKrCycleReport:
    def test_frozen_cannot_mutate(self) -> None:
        """frozen 모델은 필드 수정 시 예외."""
        report = KrCycleReport(
            cycle_id="abc123",
            started_at=_kst(2025, 5, 12, 10, 0),
            ended_at=_kst(2025, 5, 12, 10, 0, 3),
            timeframe="60",
            processed_symbols=2,
            signals_evaluated=4,
            signals_sent=1,
            failures=(),
        )
        with pytest.raises(Exception):
            report.signals_sent = 99  # type: ignore[misc]

    def test_failures_is_tuple(self) -> None:
        """failures는 tuple로 저장된다."""
        report = KrCycleReport(
            cycle_id="abc",
            started_at=_kst(2025, 5, 12, 10, 0),
            ended_at=_kst(2025, 5, 12, 10, 0, 1),
            timeframe="120",
            processed_symbols=1,
            signals_evaluated=0,
            signals_sent=0,
            failures=("005930",),
        )
        assert isinstance(report.failures, tuple)
        assert "005930" in report.failures


# ------------------------------------------------------------------ #
# run_one_cycle 테스트
# ------------------------------------------------------------------ #


class TestRunOneCycle:
    async def test_empty_candles_returns_report(self) -> None:
        """캔들이 없으면 시그널 없이 보고서를 반환한다."""
        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[])
        runner = _make_runner(exchange=exchange)

        now = _kst(2025, 5, 12, 10, 0)
        report = await runner.run_one_cycle(now, "cycle001", Timeframe.HOUR_1)

        assert report.signals_evaluated == 0
        assert report.signals_sent == 0
        assert report.timeframe == "60"

    async def test_no_symbols_in_settings_calls_list_symbols(self) -> None:
        """whitelist가 비어있으면 exchange.list_symbols()를 호출한다."""
        exchange = AsyncMock()
        exchange.list_symbols = AsyncMock(return_value=["005930"])
        exchange.fetch_candles = AsyncMock(return_value=[])
        settings = _make_settings(kr_whitelist_symbols=[])
        runner = _make_runner(exchange=exchange, settings=settings)

        now = _kst(2025, 5, 12, 10, 0)
        await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        exchange.list_symbols.assert_called_once()

    async def test_whitelist_skips_list_symbols(self) -> None:
        """whitelist가 있으면 exchange.list_symbols()를 호출하지 않는다."""
        exchange = AsyncMock()
        exchange.list_symbols = AsyncMock(return_value=["000000"])
        exchange.fetch_candles = AsyncMock(return_value=[])
        settings = _make_settings(kr_whitelist_symbols=["005930"])
        runner = _make_runner(exchange=exchange, settings=settings)

        now = _kst(2025, 5, 12, 10, 0)
        await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        exchange.list_symbols.assert_not_called()

    async def test_signal_sent_when_cooled_down(self) -> None:
        """쿨다운 통과 시그널은 notifier.send_signal이 호출된다.

        generate_snapshot을 patch해 ValueError를 발생시키면 chart_path=None으로 fallback.
        """
        symbol = "005930"
        now = _kst(2025, 5, 12, 10, 0)
        candle = _make_candle(symbol, now)
        signal = _make_signal(symbol)

        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[candle])

        strategy = MagicMock()
        strategy.evaluate = MagicMock(return_value=[signal])

        notifier = AsyncMock()
        notifier.send_signal = AsyncMock(return_value=None)

        cooldown_60m = MagicMock()
        cooldown_60m.is_cooled_down = MagicMock(return_value=True)
        cooldown_60m.mark_sent = MagicMock()

        runner = _make_runner(
            exchange=exchange,
            strategy=strategy,
            notifier=notifier,
            cooldown_60m=cooldown_60m,
            settings=_make_settings(kr_whitelist_symbols=["005930"]),
        )

        with patch(
            "signal_program.kr_runner.generate_snapshot",
            side_effect=ValueError("캔들 부족"),
        ):
            report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        notifier.send_signal.assert_called_once_with(signal, None)
        cooldown_60m.mark_sent.assert_called_once()
        assert report.signals_sent == 1

    async def test_signal_skipped_when_on_cooldown(self) -> None:
        """쿨다운 미통과 시그널은 발송하지 않는다."""
        symbol = "005930"
        now = _kst(2025, 5, 12, 10, 0)
        candle = _make_candle(symbol, now)
        signal = _make_signal(symbol)

        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[candle])

        strategy = MagicMock()
        strategy.evaluate = MagicMock(return_value=[signal])

        notifier = AsyncMock()

        cooldown_60m = MagicMock()
        cooldown_60m.is_cooled_down = MagicMock(return_value=False)

        runner = _make_runner(
            exchange=exchange,
            strategy=strategy,
            notifier=notifier,
            cooldown_60m=cooldown_60m,
            settings=_make_settings(kr_whitelist_symbols=["005930"]),
        )

        report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        notifier.send_signal.assert_not_called()
        assert report.signals_sent == 0
        assert report.signals_evaluated == 1

    async def test_hour2_uses_cooldown_120m(self) -> None:
        """HOUR_2 사이클은 cooldown_120m을 사용한다."""
        symbol = "005930"
        now = _kst(2025, 5, 12, 10, 0)
        candle = _make_candle(symbol, now)
        signal = _make_signal(symbol, Timeframe.HOUR_2)

        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[candle])

        strategy = MagicMock()
        strategy.evaluate = MagicMock(return_value=[signal])

        notifier = AsyncMock()
        notifier.send_signal = AsyncMock(return_value=None)

        cooldown_60m = MagicMock()
        cooldown_60m.is_cooled_down = MagicMock(return_value=True)

        cooldown_120m = MagicMock()
        cooldown_120m.is_cooled_down = MagicMock(return_value=True)
        cooldown_120m.mark_sent = MagicMock()

        runner = _make_runner(
            exchange=exchange,
            strategy=strategy,
            notifier=notifier,
            cooldown_60m=cooldown_60m,
            cooldown_120m=cooldown_120m,
        )

        with patch(
            "signal_program.kr_runner.generate_snapshot",
            side_effect=ValueError("캔들 부족"),
        ):
            await runner.run_one_cycle(now, "cid", Timeframe.HOUR_2)

        # HOUR_2 경로는 cooldown_120m만 사용
        cooldown_120m.is_cooled_down.assert_called()
        cooldown_60m.is_cooled_down.assert_not_called()

    async def test_fetch_failure_recorded_in_failures(self) -> None:
        """fetch_candles 예외는 failures에 기록되고 사이클은 계속된다."""
        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(side_effect=ConnectionError("timeout"))

        runner = _make_runner(exchange=exchange)

        now = _kst(2025, 5, 12, 10, 0)
        report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        assert len(report.failures) > 0

    async def test_list_symbols_failure_returns_empty_report(self) -> None:
        """list_symbols 실패 시 빈 보고서를 반환한다."""
        exchange = AsyncMock()
        exchange.list_symbols = AsyncMock(side_effect=ConnectionError("down"))
        settings = _make_settings(kr_whitelist_symbols=[])
        runner = _make_runner(exchange=exchange, settings=settings)

        now = _kst(2025, 5, 12, 10, 0)
        report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        assert report.processed_symbols == 0
        assert report.signals_sent == 0

    async def test_report_processed_symbols_matches_whitelist(self) -> None:
        """processed_symbols는 whitelist 심볼 수와 일치한다."""
        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[])
        settings = _make_settings(kr_whitelist_symbols=["005930", "000660", "035420"])
        runner = _make_runner(exchange=exchange, settings=settings)

        now = _kst(2025, 5, 12, 10, 0)
        report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        assert report.processed_symbols == 3


# ------------------------------------------------------------------ #
# run_forever 테스트
# ------------------------------------------------------------------ #


class TestRunForever:
    async def test_skips_cycle_when_market_closed(self) -> None:
        """시장 폐장 시각에는 run_one_cycle을 호출하지 않는다."""
        runner = _make_runner()
        runner.run_one_cycle = AsyncMock()  # type: ignore[method-assign]

        # 토요일 10:00 KST — 시장 폐장
        saturday_1000 = _kst(2025, 5, 10, 10, 0)
        # 다음 루프 진입 시각을 즉시 반환하도록 패치
        # run_forever는 _next_hour_top(now) + delay 만큼 sleep하므로
        # asyncio.sleep과 datetime.now를 패치해서 한 루프만 실행

        call_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with (
            patch("signal_program.kr_runner.asyncio.sleep", side_effect=fake_sleep),
            patch(
                "signal_program.kr_runner.datetime",
                wraps=__import__("datetime").datetime,
            ) as mock_dt,
        ):
            mock_dt.now = MagicMock(return_value=saturday_1000)

            with pytest.raises(asyncio.CancelledError):
                await runner.run_forever()

        runner.run_one_cycle.assert_not_called()

    async def test_hour1_always_runs_when_market_open(self) -> None:
        """시장 개장 시 HOUR_1은 항상 실행된다."""
        runner = _make_runner()
        runner.run_one_cycle = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock()
        )

        # 월요일 11:00 KST — HOUR_2 비해당
        monday_1100 = _kst(2025, 5, 12, 11, 0)
        call_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with (
            patch("signal_program.kr_runner.asyncio.sleep", side_effect=fake_sleep),
            patch("signal_program.kr_runner.datetime") as mock_dt,
        ):
            mock_dt.now = MagicMock(return_value=monday_1100)

            with pytest.raises(asyncio.CancelledError):
                await runner.run_forever()

        calls = runner.run_one_cycle.call_args_list
        timeframes = [c.args[2] for c in calls]
        assert Timeframe.HOUR_1 in timeframes

    async def test_hour2_runs_on_eligible_hours(self) -> None:
        """10, 12, 14시에는 HOUR_2도 실행된다."""
        runner = _make_runner()
        runner.run_one_cycle = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock()
        )

        # 월요일 10:00 KST — HOUR_2 해당
        monday_1000 = _kst(2025, 5, 12, 10, 0)
        call_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with (
            patch("signal_program.kr_runner.asyncio.sleep", side_effect=fake_sleep),
            patch("signal_program.kr_runner.datetime") as mock_dt,
        ):
            mock_dt.now = MagicMock(return_value=monday_1000)

            with pytest.raises(asyncio.CancelledError):
                await runner.run_forever()

        calls = runner.run_one_cycle.call_args_list
        timeframes = [c.args[2] for c in calls]
        assert Timeframe.HOUR_1 in timeframes
        assert Timeframe.HOUR_2 in timeframes

    async def test_hour2_does_not_run_on_ineligible_hours(self) -> None:
        """11, 13시 등 홀수 시각에는 HOUR_2가 실행되지 않는다."""
        runner = _make_runner()
        runner.run_one_cycle = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock()
        )

        # 월요일 11:00 KST — HOUR_2 비해당
        monday_1100 = _kst(2025, 5, 12, 11, 0)
        call_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with (
            patch("signal_program.kr_runner.asyncio.sleep", side_effect=fake_sleep),
            patch("signal_program.kr_runner.datetime") as mock_dt,
        ):
            mock_dt.now = MagicMock(return_value=monday_1100)

            with pytest.raises(asyncio.CancelledError):
                await runner.run_forever()

        calls = runner.run_one_cycle.call_args_list
        timeframes = [c.args[2] for c in calls]
        assert Timeframe.HOUR_2 not in timeframes


# ------------------------------------------------------------------ #
# M19 — 차트 생성 연동 테스트
# ------------------------------------------------------------------ #


class TestChartIntegration:
    async def test_chart_attached_on_success(self) -> None:
        """generate_snapshot 성공 시 chart_path가 send_signal에 전달된다."""
        symbol = "005930"
        now = _kst(2025, 5, 12, 10, 0)
        candle = _make_candle(symbol, now)
        signal = _make_signal(symbol)
        fake_chart = Path("/tmp/charts/chart.png")

        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[candle])

        strategy = MagicMock()
        strategy.evaluate = MagicMock(return_value=[signal])

        notifier = AsyncMock()
        notifier.send_signal = AsyncMock(return_value=None)

        cooldown = MagicMock()
        cooldown.is_cooled_down = MagicMock(return_value=True)
        cooldown.mark_sent = MagicMock()

        runner = _make_runner(
            exchange=exchange,
            strategy=strategy,
            notifier=notifier,
            cooldown_60m=cooldown,
            settings=_make_settings(kr_whitelist_symbols=["005930"]),
        )

        with patch(
            "signal_program.kr_runner.generate_snapshot",
            return_value=fake_chart,
        ):
            report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        notifier.send_signal.assert_called_once_with(signal, fake_chart)
        assert report.signals_sent == 1

    async def test_chart_none_on_snapshot_failure(self) -> None:
        """generate_snapshot 실패 시 chart_path=None으로 텍스트 알림은 계속 전송된다."""
        symbol = "005930"
        now = _kst(2025, 5, 12, 10, 0)
        candle = _make_candle(symbol, now)
        signal = _make_signal(symbol)

        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[candle])

        strategy = MagicMock()
        strategy.evaluate = MagicMock(return_value=[signal])

        notifier = AsyncMock()
        notifier.send_signal = AsyncMock(return_value=None)

        cooldown = MagicMock()
        cooldown.is_cooled_down = MagicMock(return_value=True)
        cooldown.mark_sent = MagicMock()

        runner = _make_runner(
            exchange=exchange,
            strategy=strategy,
            notifier=notifier,
            cooldown_60m=cooldown,
            settings=_make_settings(kr_whitelist_symbols=["005930"]),
        )

        with patch(
            "signal_program.kr_runner.generate_snapshot",
            side_effect=ValueError("캔들 수 부족: 200 필요, 1 보유"),
        ):
            report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        # 차트 실패해도 텍스트 알림은 전송
        notifier.send_signal.assert_called_once_with(signal, None)
        assert report.signals_sent == 1
        assert len(report.failures) == 0

    async def test_chart_none_on_unexpected_exception(self) -> None:
        """generate_snapshot이 예상치 못한 예외를 던져도 send_signal은 호출된다."""
        symbol = "005930"
        now = _kst(2025, 5, 12, 10, 0)
        candle = _make_candle(symbol, now)
        signal = _make_signal(symbol)

        exchange = AsyncMock()
        exchange.fetch_candles = AsyncMock(return_value=[candle])

        strategy = MagicMock()
        strategy.evaluate = MagicMock(return_value=[signal])

        notifier = AsyncMock()
        notifier.send_signal = AsyncMock(return_value=None)

        cooldown = MagicMock()
        cooldown.is_cooled_down = MagicMock(return_value=True)
        cooldown.mark_sent = MagicMock()

        runner = _make_runner(
            exchange=exchange,
            strategy=strategy,
            notifier=notifier,
            cooldown_60m=cooldown,
            settings=_make_settings(kr_whitelist_symbols=["005930"]),
        )

        with patch(
            "signal_program.kr_runner.generate_snapshot",
            side_effect=RuntimeError("matplotlib 오류"),
        ):
            report = await runner.run_one_cycle(now, "cid", Timeframe.HOUR_1)

        notifier.send_signal.assert_called_once_with(signal, None)
        assert report.signals_sent == 1
