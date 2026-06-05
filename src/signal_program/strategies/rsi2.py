"""Rsi2Strategy — Connors RSI(2) 평균회귀 + 추세필터 (설계 v2.3 §3.3, StrategyMode.F).

매수: close > sma(trend_period) AND rsi2 < rsi2_oversold(10)
매도: close < sma(trend_period) AND rsi2 > rsi2_overbought(90)
STRONG: rsi2 < 5 (매수) / rsi2 > 95 (매도)

트레이더 노트: 추세필터가 이 전략의 전부다. 필터 없는 RSI(2)는 하락장에서 계좌를
갈아먹는다. 캔들 < trend_period+1 이면 신호 없음(예외 아님).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.indicators.rsi import rsi
from signal_program.models import IndicatorSnapshot, Signal
from signal_program.strategies.base import calc_change_pct

if TYPE_CHECKING:
    from datetime import datetime

_KST = ZoneInfo("Asia/Seoul")

#: STRONG 강도 경계 (oversold/overbought 안쪽 극단)
_STRONG_OVERSOLD = 5.0
_STRONG_OVERBOUGHT = 95.0


class Rsi2Strategy:
    """RSI(2) 평균회귀 전략 (StrategyMode.RSI2_REVERSION)."""

    name = "v5_rsi2"

    def __init__(
        self,
        rsi2_period: int = 2,
        rsi2_oversold: float = 10.0,
        rsi2_overbought: float = 90.0,
        rsi2_trend_period: int = 200,
        volume_lookback: int = 20,
    ) -> None:
        self.rsi2_period = rsi2_period
        self.oversold = rsi2_oversold
        self.overbought = rsi2_overbought
        self.trend_period = rsi2_trend_period
        self._volume_lookback = volume_lookback

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]:
        # 추세 SMA 계산에 trend_period 봉 + 직전봉 1개 필요 → 부족 시 무신호 (예외 아님)
        if len(candles) < self.trend_period + 1:
            return []

        close = candles["close"]
        close_last = float(close.iloc[-1])

        trend_sma = float(close.rolling(self.trend_period).mean().iloc[-1])
        rsi2_val = float(rsi(close, self.rsi2_period).iloc[-1])
        if math.isnan(trend_sma) or math.isnan(rsi2_val):
            return []

        vol_mean = float(candles["volume"].iloc[-self._volume_lookback - 1 : -1].mean())
        volume_ratio = float(candles["volume"].iloc[-1]) / vol_mean if vol_mean > 0 else 0.0

        raw_ts = candles["opened_at"].iloc[-1]
        dt: datetime = raw_ts.to_pydatetime() if isinstance(raw_ts, pd.Timestamp) else raw_ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)

        chg = calc_change_pct(candles)
        signals: list[Signal] = []

        if close_last > trend_sma and rsi2_val < self.oversold:
            strength = (
                SignalStrength.STRONG if rsi2_val < _STRONG_OVERSOLD else SignalStrength.NORMAL
            )
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.BUY,
                    strength,
                    close_last,
                    dt,
                    volume_ratio,
                    rsi2_val,
                    trend_sma,
                    chg,
                )
            )
        if close_last < trend_sma and rsi2_val > self.overbought:
            strength = (
                SignalStrength.STRONG if rsi2_val > _STRONG_OVERBOUGHT else SignalStrength.NORMAL
            )
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.SELL,
                    strength,
                    close_last,
                    dt,
                    volume_ratio,
                    rsi2_val,
                    trend_sma,
                    chg,
                )
            )
        return signals

    def _build_signal(
        self,
        market: str,
        direction: SignalDirection,
        strength: SignalStrength,
        price: float,
        triggered_at: datetime,
        volume_ratio: float,
        rsi2_val: float,
        trend_sma: float,
        change_pct: float | None,
    ) -> Signal:
        return Signal(
            market=market,
            timeframe=Timeframe.HOUR_1,
            mode=StrategyMode.RSI2_REVERSION,
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
                rsi2=rsi2_val,
                trend_sma=trend_sma,
            ),
            change_pct=change_pct,
        )
