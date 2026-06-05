"""DonchianStrategy — 터틀식 추세추종 (설계 v2.3 §3.2, StrategyMode.E).

매수: close > dc_upper(entry_period=20)   매도: close < dc_lower(exit_period=10)
STRONG: volume_ratio >= donchian_volume_strong(1.5).

트레이더 노트: 거래량은 진입 게이트가 아니라 강도 표시에만 쓴다. 추세추종은
신호를 거르는 게 아니라 손절을 짧게 가져가는 전략이다 (포지션·손절은 비목표).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.indicators.donchian import donchian
from signal_program.models import IndicatorSnapshot, Signal
from signal_program.strategies.base import calc_change_pct

if TYPE_CHECKING:
    from datetime import datetime

_KST = ZoneInfo("Asia/Seoul")


class DonchianStrategy:
    """Donchian 채널 돌파 전략 (StrategyMode.DONCHIAN_BREAKOUT)."""

    name = "v4_donchian"

    def __init__(
        self,
        donchian_entry_period: int = 20,
        donchian_exit_period: int = 10,
        donchian_volume_strong: float = 1.5,
        volume_lookback: int = 20,
    ) -> None:
        self.entry_period = donchian_entry_period
        self.exit_period = donchian_exit_period
        self.volume_strong = donchian_volume_strong
        self._volume_lookback = volume_lookback

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]:
        min_len = max(self.entry_period, self.exit_period, self._volume_lookback) + 1
        if len(candles) < min_len:
            return []

        high = candles["high"]
        low = candles["low"]
        close_last = float(candles["close"].iloc[-1])

        entry_ch = donchian(high, low, self.entry_period)
        exit_ch = donchian(high, low, self.exit_period)
        dc_upper = float(entry_ch["dc_upper"].iloc[-1])
        dc_lower = float(exit_ch["dc_lower"].iloc[-1])
        if math.isnan(dc_upper) or math.isnan(dc_lower):
            return []

        vol_mean = float(candles["volume"].iloc[-self._volume_lookback - 1 : -1].mean())
        volume_ratio = float(candles["volume"].iloc[-1]) / vol_mean if vol_mean > 0 else 0.0

        raw_ts = candles["opened_at"].iloc[-1]
        dt: datetime = raw_ts.to_pydatetime() if isinstance(raw_ts, pd.Timestamp) else raw_ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)

        chg = calc_change_pct(candles)
        signals: list[Signal] = []

        if close_last > dc_upper:
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.BUY,
                    close_last,
                    dt,
                    volume_ratio,
                    dc_upper,
                    dc_lower,
                    chg,
                )
            )
        if close_last < dc_lower:
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.SELL,
                    close_last,
                    dt,
                    volume_ratio,
                    dc_upper,
                    dc_lower,
                    chg,
                )
            )
        return signals

    def _build_signal(
        self,
        market: str,
        direction: SignalDirection,
        price: float,
        triggered_at: datetime,
        volume_ratio: float,
        dc_upper: float,
        dc_lower: float,
        change_pct: float | None,
    ) -> Signal:
        strength = (
            SignalStrength.STRONG if volume_ratio >= self.volume_strong else SignalStrength.NORMAL
        )
        return Signal(
            market=market,
            timeframe=Timeframe.HOUR_1,
            mode=StrategyMode.DONCHIAN_BREAKOUT,
            direction=direction,
            strength=strength,
            price=price,
            triggered_at=triggered_at,
            indicators=IndicatorSnapshot(
                bb_upper=0.0,
                bb_middle=0.0,
                bb_lower=0.0,
                bb_width=0.0,
                bb_pct_b=0.0,
                cci=0.0,
                volume_ratio=volume_ratio,
                dc_upper=dc_upper,
                dc_lower=dc_lower,
            ),
            change_pct=change_pct,
        )
