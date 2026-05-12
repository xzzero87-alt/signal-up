"""RunnerService — 1시간봉 마감마다 전략 평가·알림 사이클 실행."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence  # noqa: TC003
from datetime import datetime, timedelta
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from pydantic import BaseModel, ConfigDict

from signal_program.charting.snapshot import generate_snapshot
from signal_program.config import Settings  # noqa: TC001
from signal_program.enums import Timeframe
from signal_program.state.cooldown import CooldownKey, CooldownStore
from signal_program.state.signal_log import SignalLog  # noqa: TC001

if TYPE_CHECKING:
    from signal_program.exchanges.base import Exchange
    from signal_program.notifiers.base import Notifier
    from signal_program.strategies.base import Strategy

_KST = ZoneInfo("Asia/Seoul")
log = structlog.get_logger()


class CycleReport(BaseModel):
    """단일 사이클 실행 결과 요약."""

    model_config = ConfigDict(frozen=True)

    cycle_id: str
    started_at: datetime
    ended_at: datetime
    processed_markets: int
    signals_evaluated: int
    signals_sent: int
    failures: tuple[str, ...]


def _next_hour_top(dt: datetime) -> datetime:
    """dt 이후 첫 정시(분·초=0) 반환."""
    return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def candles_to_df(candles: Sequence[Any]) -> pd.DataFrame:
    """list[Candle] → DataFrame (columns: market, opened_at, open, high, low, close, volume, quote_volume)."""  # noqa: E501
    return pd.DataFrame([c.model_dump() for c in candles])


class RunnerService:
    """컴포넌트 조립 및 사이클 실행 오케스트레이터."""

    def __init__(
        self,
        settings: Settings,
        exchange: Exchange,
        strategy: Strategy,
        cooldown: CooldownStore,
        notifier: Notifier,
        signal_log: SignalLog,
        charts_dir: Path,
    ) -> None:
        self._settings = settings
        self._exchange = exchange
        self._strategy = strategy
        self._cooldown = cooldown
        self._notifier = notifier
        self._signal_log = signal_log
        self._charts_dir = charts_dir

    async def run_one_cycle(self, now: datetime, cycle_id: str) -> CycleReport:
        """화이트리스트 전체를 Semaphore(5) 동시 처리 후 CycleReport 반환."""
        structlog.contextvars.bind_contextvars(cycle_id=cycle_id)
        log.info("cycle_start", markets=len(self._settings.whitelist_markets))

        sem = asyncio.Semaphore(5)
        signals_evaluated = 0
        signals_sent = 0
        failures: list[str] = []

        async def _process_market(market: str) -> None:
            nonlocal signals_evaluated, signals_sent
            async with sem:
                try:
                    candles = await self._exchange.fetch_candles(market, Timeframe.HOUR_1, 200)
                    if not candles:
                        return

                    df = candles_to_df(candles)
                    signals = self._strategy.evaluate(market, df)
                    signals_evaluated += len(signals)

                    for signal in signals:
                        key = CooldownKey(market, signal.mode, signal.direction)
                        if self._cooldown.is_cooled_down(key, now):
                            log.info("signal_cooled_down", market=market)
                            await self._signal_log.append(signal, "cooled_down", now)
                            continue

                        chart_path = None
                        try:
                            chart_path = generate_snapshot(df, signal, self._charts_dir)
                        except Exception as exc:
                            log.error("chart_failed", market=market, error=str(exc))

                        await self._notifier.send_signal(signal, chart_path)
                        sent_status = "dry_run" if self._settings.dry_run else "ok"

                        if not self._settings.dry_run:
                            self._cooldown.mark_sent(key, now)

                        await self._signal_log.append(signal, sent_status, now)
                        signals_sent += 1

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("market_failed", market=market, error=str(exc))
                    failures.append(f"{market}: {exc}")

        await asyncio.gather(*[_process_market(m) for m in self._settings.whitelist_markets])

        ended_at = datetime.now(_KST)
        report = CycleReport(
            cycle_id=cycle_id,
            started_at=now,
            ended_at=ended_at,
            processed_markets=len(self._settings.whitelist_markets),
            signals_evaluated=signals_evaluated,
            signals_sent=signals_sent,
            failures=tuple(failures),
        )
        log.info(
            "cycle_end",
            signals_evaluated=signals_evaluated,
            signals_sent=signals_sent,
            failures=len(failures),
        )
        structlog.contextvars.unbind_contextvars("cycle_id")
        return report

    async def run_forever(self) -> None:
        """정시 +cycle_delay_seconds마다 사이클 실행. cycle_delay_seconds=0이면 즉시 시작."""
        log.info("runner_start")
        try:
            while True:
                if self._settings.cycle_delay_seconds > 0:
                    now = datetime.now(_KST)
                    next_run = _next_hour_top(now) + timedelta(
                        seconds=self._settings.cycle_delay_seconds
                    )
                    sleep_sec = (next_run - now).total_seconds()
                    if sleep_sec > 0:
                        log.info("runner_sleeping", seconds=round(sleep_sec))
                        await asyncio.sleep(sleep_sec)

                cycle_id = uuid4().hex[:12]
                try:
                    await asyncio.wait_for(
                        self.run_one_cycle(datetime.now(_KST), cycle_id),
                        timeout=float(self._settings.cycle_timeout_seconds),
                    )
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    log.error("cycle_timeout", cycle_id=cycle_id)
                except Exception:
                    log.exception("cycle_failed", cycle_id=cycle_id)

                # cycle_delay=0일 때도 이벤트루프가 타임아웃·외부 cancel 처리할 기회를 준다
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            log.info("runner_stopped")
            raise
