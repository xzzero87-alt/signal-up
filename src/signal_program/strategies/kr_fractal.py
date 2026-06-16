"""국내 주식 전용 전략 — Williams Fractal Breakout (ADR-0018)."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.indicators.fractal import find_fractals as _find_fractals
from signal_program.models import IndicatorSnapshot, Signal
from signal_program.strategies.base import calc_change_pct

_KST = ZoneInfo("Asia/Seoul")
_20H = timedelta(hours=20)  # 일봉 판별 임계치 (주말 포함 최소 간격 20h)
_90M = timedelta(minutes=90)


def _infer_timeframe(candles: pd.DataFrame) -> Timeframe:
    if len(candles) < 2:
        return Timeframe.HOUR_1
    delta = candles["opened_at"].iloc[-1] - candles["opened_at"].iloc[-2]
    if delta >= _20H:
        return Timeframe.DAY
    return Timeframe.HOUR_2 if delta >= _90M else Timeframe.HOUR_1


class KrFractalStrategy:
    """Williams Fractal Breakout + 거래량 필터 전략 (StrategyMode.D)."""

    name = "kr_fractal_v1"

    def __init__(
        self,
        fractal_lookback: int = 100,
        fractal_volume_threshold: float = 1.2,
        fractal_volume_strong: float = 2.0,
        volume_lookback: int = 20,
    ) -> None:
        self.fractal_lookback = fractal_lookback
        self.fractal_volume_threshold = fractal_volume_threshold
        self.fractal_volume_strong = fractal_volume_strong
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

        up_level, up_age, down_level, down_age = _find_fractals(candles, self.fractal_lookback)

        raw_ts = candles["opened_at"].iloc[-1]
        dt = raw_ts.to_pydatetime() if isinstance(raw_ts, pd.Timestamp) else raw_ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)

        timeframe = _infer_timeframe(candles)
        signals: list[Signal] = []
        chg = calc_change_pct(candles)

        if up_level is not None and close_last > up_level:
            strength = (
                SignalStrength.STRONG
                if volume_ratio >= self.fractal_volume_strong
                else SignalStrength.NORMAL
            )
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.BUY,
                    strength,
                    close_last,
                    dt,
                    timeframe,
                    volume_ratio,
                    up_level,
                    up_age,
                    down_level,
                    down_age,
                    change_pct=chg,
                )
            )

        if down_level is not None and close_last < down_level:
            strength = (
                SignalStrength.STRONG
                if volume_ratio >= self.fractal_volume_strong
                else SignalStrength.NORMAL
            )
            signals.append(
                self._build_signal(
                    market,
                    SignalDirection.SELL,
                    strength,
                    close_last,
                    dt,
                    timeframe,
                    volume_ratio,
                    up_level,
                    up_age,
                    down_level,
                    down_age,
                    change_pct=chg,
                )
            )

        return signals

    def _build_signal(
        self,
        market: str,
        direction: SignalDirection,
        strength: SignalStrength,
        price: float,
        triggered_at: object,
        timeframe: Timeframe,
        volume_ratio: float,
        fractal_up: float | None,
        fractal_up_age: int,
        fractal_down: float | None,
        fractal_down_age: int,
        change_pct: float | None = None,
    ) -> Signal:
        return Signal(
            market=market,
            timeframe=timeframe,
            mode=StrategyMode.FRACTAL_BREAKOUT,
            direction=direction,
            strength=strength,
            price=price,
            triggered_at=triggered_at,  # type: ignore[arg-type]
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
