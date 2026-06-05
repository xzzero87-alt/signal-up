"""FractalStrategy — 암호화폐용 Williams Fractal 돌파 (설계 v2.3 §3.1, StrategyMode.D).

KrFractalStrategy(ADR-0018) 로직을 마켓 중립으로 일반화한다.
- 프랙탈 확정 규칙은 공용 모듈(indicators.fractal.find_fractals)로 동일.
- 국장 전용 가정(타임프레임 추론)은 제외 → 고정 1시간봉.
- KrFractal에 없는 fractal_max_age 필터 추가 (stale 프랙탈 배제).

매수: close > 최근 확정 up-fractal + volume_ratio >= fractal_volume_threshold(1.2)
매도: close < 최근 확정 down-fractal + 동일 거래량 필터
STRONG: volume_ratio >= fractal_volume_strong(2.0)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.indicators.fractal import find_fractals
from signal_program.models import IndicatorSnapshot, Signal
from signal_program.strategies.base import calc_change_pct

if TYPE_CHECKING:
    from datetime import datetime

_KST = ZoneInfo("Asia/Seoul")


class FractalStrategy:
    """암호화폐 Williams Fractal 돌파 전략 (StrategyMode.FRACTAL_BREAKOUT)."""

    name = "v3_fractal"

    def __init__(
        self,
        fractal_lookback: int = 100,
        fractal_volume_threshold: float = 1.2,
        fractal_volume_strong: float = 2.0,
        fractal_max_age: int = 20,
        volume_lookback: int = 20,
    ) -> None:
        self.fractal_lookback = fractal_lookback
        self.fractal_volume_threshold = fractal_volume_threshold
        self.fractal_volume_strong = fractal_volume_strong
        self.fractal_max_age = fractal_max_age
        self._volume_lookback = volume_lookback

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]:
        min_len = max(7, self._volume_lookback + 3)
        if len(candles) < min_len:
            return []

        close_last = float(candles["close"].iloc[-1])
        vol_mean = float(candles["volume"].iloc[-self._volume_lookback - 1 : -1].mean())
        volume_ratio = float(candles["volume"].iloc[-1]) / vol_mean if vol_mean > 0 else 0.0

        if volume_ratio < self.fractal_volume_threshold:
            return []

        up_level, up_age, down_level, down_age = find_fractals(candles, self.fractal_lookback)

        # stale 프랙탈 배제 (KrFractal엔 없는 규율)
        if up_level is not None and up_age > self.fractal_max_age:
            up_level = None
        if down_level is not None and down_age > self.fractal_max_age:
            down_level = None

        raw_ts = candles["opened_at"].iloc[-1]
        dt: datetime = raw_ts.to_pydatetime() if isinstance(raw_ts, pd.Timestamp) else raw_ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)

        chg = calc_change_pct(candles)
        signals: list[Signal] = []

        if up_level is not None and close_last > up_level:
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.BUY,
                    close_last,
                    dt,
                    volume_ratio,
                    up_level,
                    up_age,
                    down_level,
                    down_age,
                    chg,
                )
            )
        if down_level is not None and close_last < down_level:
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.SELL,
                    close_last,
                    dt,
                    volume_ratio,
                    up_level,
                    up_age,
                    down_level,
                    down_age,
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
        fractal_up: float | None,
        fractal_up_age: int,
        fractal_down: float | None,
        fractal_down_age: int,
        change_pct: float | None,
    ) -> Signal:
        strength = (
            SignalStrength.STRONG
            if volume_ratio >= self.fractal_volume_strong
            else SignalStrength.NORMAL
        )
        return Signal(
            market=market,
            timeframe=Timeframe.HOUR_1,
            mode=StrategyMode.FRACTAL_BREAKOUT,
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
                fractal_up=fractal_up,
                fractal_down=fractal_down,
                fractal_up_age=fractal_up_age if fractal_up is not None else None,
                fractal_down_age=fractal_down_age if fractal_down is not None else None,
            ),
            change_pct=change_pct,
        )
