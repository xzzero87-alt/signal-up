"""국내 주식(KIS) 스캔 루프 서비스."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from pydantic import BaseModel, ConfigDict

from signal_program.config import Settings
from signal_program.enums import Timeframe
from signal_program.exchanges.kis_api import KoreanStockExchange
from signal_program.notifiers.base import Notifier
from signal_program.charting.snapshot import generate_snapshot
from signal_program.runner import candles_to_df
from signal_program.state.signal_log import SignalLog
from signal_program.state.cooldown import CooldownKey, CooldownStore
from signal_program.strategies.base import Strategy

log = structlog.get_logger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_MARKET_OPEN = time(9, 0)
_MARKET_CLOSE = time(15, 30)

# HOUR_2 대상 시간대: 짝수 시, 10~14시 (10, 12, 14시 봉 마감 후)
_HOUR_2_ELIGIBLE = frozenset({10, 12, 14})

_KR_RUNNER_SEMAPHORE_COUNT = 3  # KIS 자체 세마포어가 있으므로 업비트보다 낮게


def _is_market_open(now: datetime) -> bool:
    """KST 기준 국내 주식시장 개장 여부를 반환한다.

    Args:
        now: 현재 시각 (timezone-aware datetime).

    Returns:
        평일 09:00 ~ 15:30(미포함) 사이이면 True, 그 외 False.
    """
    kst_now = now.astimezone(_KST)
    if kst_now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = kst_now.time()
    return _MARKET_OPEN <= t < _MARKET_CLOSE


def _next_hour_top(dt: datetime) -> datetime:
    """주어진 시각 이후 첫 정각(분·초·마이크로초 = 0)을 반환한다."""
    return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


class KrCycleReport(BaseModel):
    """국내 주식 스캔 사이클 결과 요약."""

    model_config = ConfigDict(frozen=True)

    cycle_id: str
    started_at: datetime
    ended_at: datetime
    timeframe: str
    processed_symbols: int
    signals_evaluated: int
    signals_sent: int
    failures: tuple[str, ...]


class KrStockRunnerService:
    """국내 주식 심볼을 대상으로 시그널을 주기적으로 스캔하는 서비스.

    RunnerService(업비트 코인)와 병렬로 실행되며, KIS API를 통해
    HOUR_1(60분봉) 및 HOUR_2(120분봉) 타임프레임을 처리한다.
    """

    def __init__(
        self,
        settings: Settings,
        exchange: KoreanStockExchange,
        strategy: Strategy,
        notifier: Notifier,
        signal_log: SignalLog,
        cooldown_60m: CooldownStore,
        cooldown_120m: CooldownStore,
        charts_dir: Path,
    ) -> None:
        self._settings = settings
        self._exchange = exchange
        self._strategy = strategy
        self._notifier = notifier
        self._signal_log = signal_log
        self._cooldown_60m = cooldown_60m
        self._cooldown_120m = cooldown_120m
        self._charts_dir = charts_dir
        self._semaphore = asyncio.Semaphore(_KR_RUNNER_SEMAPHORE_COUNT)

    async def _process_symbol(
        self,
        symbol: str,
        timeframe: Timeframe,
        cooldown: CooldownStore,
        now: datetime,
        cycle_id: str,
    ) -> tuple[int, int, list[str]]:
        """단일 심볼을 처리하고 (평가 수, 발송 수, 실패 목록)을 반환한다.

        Args:
            symbol: KIS 심볼 코드 (예: "005930").
            timeframe: 처리할 타임프레임 (HOUR_1 또는 HOUR_2).
            cooldown: 해당 타임프레임의 쿨다운 스토어.
            now: 현재 KST 기준 datetime.
            cycle_id: 현재 사이클 ID (로깅용).

        Returns:
            (signals_evaluated, signals_sent, failures) 튜플.
        """
        evaluated = 0
        sent = 0
        failures: list[str] = []

        async with self._semaphore:
            try:
                candles = await self._exchange.fetch_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    count=200,
                )
            except Exception:
                log.exception(
                    "kr_fetch_failed",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    timeframe=timeframe.value,
                )
                failures.append(symbol)
                return evaluated, sent, failures

        if not candles:
            log.warning(
                "kr_no_candles",
                cycle_id=cycle_id,
                symbol=symbol,
                timeframe=timeframe.value,
            )
            return evaluated, sent, failures

        df: pd.DataFrame = candles_to_df(candles)
        signals = self._strategy.evaluate(symbol, df)
        evaluated += len(signals)

        for signal in signals:
            key = CooldownKey(
                market=symbol,
                mode=signal.mode,
                direction=signal.direction,
            )
            if not cooldown.is_cooled_down(key, now):
                log.debug(
                    "kr_signal_cooled_down",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    direction=signal.direction,
                )
                continue

            # 차트 생성 (실패해도 텍스트 알림은 계속 진행)
            chart_path = None
            try:
                chart_path = generate_snapshot(df, signal, self._charts_dir)
            except Exception:
                log.error(
                    "kr_chart_failed",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    timeframe=timeframe.value,
                )

            try:
                await self._notifier.send_signal(signal, chart_path)
                cooldown.mark_sent(key, now)
                self._signal_log.append(signal)
                sent += 1
                log.info(
                    "kr_signal_sent",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    direction=signal.direction,
                    timeframe=timeframe.value,
                    chart_attached=chart_path is not None,
                )
            except Exception:
                log.exception(
                    "kr_notify_failed",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    direction=signal.direction,
                )
                failures.append(f"{symbol}:notify")

        return evaluated, sent, failures

    async def run_one_cycle(
        self,
        now: datetime,
        cycle_id: str,
        timeframe: Timeframe,
    ) -> KrCycleReport:
        """지정된 타임프레임으로 모든 심볼을 한 번 스캔한다.

        Args:
            now: 현재 KST datetime (스케줄러에서 주입).
            cycle_id: 로깅/추적용 고유 ID.
            timeframe: HOUR_1 또는 HOUR_2.

        Returns:
            스캔 결과 요약 KrCycleReport.
        """
        started_at = now
        cooldown = (
            self._cooldown_60m if timeframe == Timeframe.HOUR_1 else self._cooldown_120m
        )

        symbols = self._settings.kr_whitelist_symbols or []
        if not symbols:
            try:
                symbols = await self._exchange.list_symbols()
            except Exception:
                log.exception("kr_list_symbols_failed", cycle_id=cycle_id)
                return KrCycleReport(
                    cycle_id=cycle_id,
                    started_at=started_at,
                    ended_at=datetime.now(_KST),
                    timeframe=timeframe.value,
                    processed_symbols=0,
                    signals_evaluated=0,
                    signals_sent=0,
                    failures=(),
                )

        log.info(
            "kr_cycle_started",
            cycle_id=cycle_id,
            timeframe=timeframe.value,
            symbol_count=len(symbols),
        )

        tasks = [
            self._process_symbol(symbol, timeframe, cooldown, now, cycle_id)
            for symbol in symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_evaluated = 0
        total_sent = 0
        all_failures: list[str] = []

        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                log.exception(
                    "kr_symbol_task_failed",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    exc_info=result,
                )
                all_failures.append(symbol)
                continue
            evaluated, sent, failures = result
            total_evaluated += evaluated
            total_sent += sent
            all_failures.extend(failures)

        ended_at = datetime.now(_KST)
        report = KrCycleReport(
            cycle_id=cycle_id,
            started_at=started_at,
            ended_at=ended_at,
            timeframe=timeframe.value,
            processed_symbols=len(symbols),
            signals_evaluated=total_evaluated,
            signals_sent=total_sent,
            failures=tuple(all_failures),
        )

        duration_ms = (ended_at - started_at).total_seconds() * 1000
        log.info(
            "kr_cycle_completed",
            cycle_id=cycle_id,
            timeframe=timeframe.value,
            processed_symbols=report.processed_symbols,
            signals_sent=report.signals_sent,
            failures=len(all_failures),
            duration_ms=round(duration_ms, 1),
        )
        return report

    async def run_forever(self) -> None:
        """시장 개장 시간대에 매 정각마다 스캔 사이클을 실행한다.

        스케줄:
        - HOUR_1 (60분봉): 시장 개장 시 매 정각 실행
        - HOUR_2 (120분봉): 짝수 정각(10, 12, 14시)에 추가 실행
        """
        log.info("kr_runner_started")
        while True:
            now = datetime.now(_KST)
            next_run = _next_hour_top(now) + timedelta(
                seconds=self._settings.cycle_delay_seconds
            )
            sleep_sec = (next_run - now).total_seconds()
            if sleep_sec > 0:
                await asyncio.sleep(sleep_sec)

            now = datetime.now(_KST)

            if not _is_market_open(now):
                log.debug("kr_market_closed", kst_hour=now.hour, weekday=now.weekday())
                await asyncio.sleep(0)
                continue

            kst_hour = now.hour
            cycle_id = uuid4().hex[:12]

            # HOUR_1: 시장 개장 시 매 정각
            try:
                await asyncio.wait_for(
                    self.run_one_cycle(now, cycle_id, Timeframe.HOUR_1),
                    timeout=float(self._settings.cycle_timeout_seconds),
                )
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                log.error(
                    "kr_cycle_timeout",
                    cycle_id=cycle_id,
                    timeframe=Timeframe.HOUR_1.value,
                )
            except Exception:
                log.exception(
                    "kr_cycle_failed",
                    cycle_id=cycle_id,
                    timeframe=Timeframe.HOUR_1.value,
                )

            # HOUR_2: 짝수 정각(10, 12, 14시)에만 추가 실행
            if kst_hour in _HOUR_2_ELIGIBLE:
                cycle_id_2 = uuid4().hex[:12]
                try:
                    await asyncio.wait_for(
                        self.run_one_cycle(now, cycle_id_2, Timeframe.HOUR_2),
                        timeout=float(self._settings.cycle_timeout_seconds),
                    )
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    log.error(
                        "kr_cycle_timeout",
                        cycle_id=cycle_id_2,
                        timeframe=Timeframe.HOUR_2.value,
                    )
                except Exception:
                    log.exception(
                        "kr_cycle_failed",
                        cycle_id=cycle_id_2,
                        timeframe=Timeframe.HOUR_2.value,
                    )

            await asyncio.sleep(0)
