from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.indicators.bollinger import bollinger
from signal_program.indicators.cci import cci
from signal_program.models import IndicatorSnapshot, Signal

_KST = ZoneInfo("Asia/Seoul")


class BbCciStrategy:
    name = "bb_cci"

    def __init__(
        self,
        bb_period: int = 20,
        bb_std_mult: float = 2.0,
        cci_period: int = 20,
        cci_threshold_normal: int = 100,
        cci_threshold_strong: int = 200,
        volume_ratio_min_a: float = 1.0,
        volume_lookback: int = 20,
    ) -> None:
        self.bb_period = bb_period
        self.bb_std_mult = bb_std_mult
        self.cci_period = cci_period
        self.cci_threshold_normal = cci_threshold_normal
        self.cci_threshold_strong = cci_threshold_strong
        self.volume_ratio_min_a = volume_ratio_min_a
        self.volume_lookback = volume_lookback

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]:
        min_len = max(self.bb_period, self.cci_period) + self.volume_lookback
        if len(candles) < min_len:
            return []

        close = candles["close"]
        high = candles["high"]
        low = candles["low"]
        volume = candles["volume"]

        bb_df = bollinger(close, self.bb_period, self.bb_std_mult)
        cci_series = cci(high, low, close, self.cci_period)

        bb_upper = float(bb_df["bb_upper"].iloc[-1])
        bb_middle = float(bb_df["bb_middle"].iloc[-1])
        bb_lower = float(bb_df["bb_lower"].iloc[-1])
        bb_width = float(bb_df["bb_width"].iloc[-1])
        bb_pct_b = float(bb_df["bb_pct_b"].iloc[-1])
        cci_val = float(cci_series.iloc[-1])
        close_last = float(close.iloc[-1])

        vol_mean = float(volume.iloc[-self.volume_lookback - 1 : -1].mean())
        volume_ratio = float(volume.iloc[-1]) / vol_mean if vol_mean > 0 else 0.0

        raw_ts = candles["opened_at"].iloc[-1]
        if isinstance(raw_ts, pd.Timestamp):
            dt = raw_ts.to_pydatetime()
        else:
            dt = raw_ts  # type: ignore[assignment]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)

        signals: list[Signal] = []

        buy = self._check_buy(close_last, bb_lower, cci_val, volume_ratio)
        if buy is not None:
            signals.append(
                self._build_signal(
                    market, buy, close_last, dt,
                    bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b,
                    cci_val, volume_ratio,
                )
            )

        sell = self._check_sell(close_last, bb_upper, cci_val, volume_ratio)
        if sell is not None:
            signals.append(
                self._build_signal(
                    market, sell, close_last, dt,
                    bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b,
                    cci_val, volume_ratio,
                )
            )

        return signals

    def _check_buy(
        self,
        close: float,
        bb_lower: float,
        cci_val: float,
        volume_ratio: float,
    ) -> tuple[SignalDirection, SignalStrength] | None:
        if not (
            close <= bb_lower
            and cci_val <= -self.cci_threshold_normal
            and volume_ratio >= self.volume_ratio_min_a
        ):
            return None
        strength = (
            SignalStrength.STRONG
            if abs(cci_val) >= self.cci_threshold_strong
            else SignalStrength.NORMAL
        )
        return (SignalDirection.BUY, strength)

    def _check_sell(
        self,
        close: float,
        bb_upper: float,
        cci_val: float,
        volume_ratio: float,
    ) -> tuple[SignalDirection, SignalStrength] | None:
        if not (
            close >= bb_upper
            and cci_val >= self.cci_threshold_normal
            and volume_ratio >= self.volume_ratio_min_a
        ):
            return None
        strength = (
            SignalStrength.STRONG
            if abs(cci_val) >= self.cci_threshold_strong
            else SignalStrength.NORMAL
        )
        return (SignalDirection.SELL, strength)

    def _build_signal(
        self,
        market: str,
        direction_strength: tuple[SignalDirection, SignalStrength],
        price: float,
        triggered_at: object,
        bb_upper: float,
        bb_middle: float,
        bb_lower: float,
        bb_width: float,
        bb_pct_b: float,
        cci_val: float,
        volume_ratio: float,
    ) -> Signal:
        from datetime import datetime

        direction, strength = direction_strength
        dt: datetime = triggered_at  # type: ignore[assignment]

        return Signal(
            market=market,
            timeframe=Timeframe.HOUR_1,
            mode=StrategyMode.MEAN_REVERSION,
            direction=direction,
            strength=strength,
            price=price,
            triggered_at=dt,
            indicators=IndicatorSnapshot(
                bb_upper=bb_upper,
                bb_middle=bb_middle,
                bb_lower=bb_lower,
                bb_width=bb_width,
                bb_pct_b=bb_pct_b,
                cci=cci_val,
                volume_ratio=volume_ratio,
                bb_width_quantile=None,
            ),
        )
