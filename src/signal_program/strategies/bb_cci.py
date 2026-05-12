from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

if TYPE_CHECKING:
    from datetime import datetime

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
        squeeze_lookback: int = 120,
        squeeze_quantile: float = 0.20,
        volume_ratio_min_b: float = 1.5,
    ) -> None:
        self.bb_period = bb_period
        self.bb_std_mult = bb_std_mult
        self.cci_period = cci_period
        self.cci_threshold_normal = cci_threshold_normal
        self.cci_threshold_strong = cci_threshold_strong
        self.volume_ratio_min_a = volume_ratio_min_a
        self.volume_lookback = volume_lookback
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_quantile = squeeze_quantile
        self.volume_ratio_min_b = volume_ratio_min_b

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]:
        min_len_a = max(self.bb_period, self.cci_period) + self.volume_lookback
        if len(candles) < min_len_a:
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
        dt = raw_ts.to_pydatetime() if isinstance(raw_ts, pd.Timestamp) else raw_ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)

        signals: list[Signal] = []

        # ── 모드 A: 평균회귀 ──────────────────────────────────────────────────
        buy_a = self._check_buy(close_last, bb_lower, cci_val, volume_ratio)
        if buy_a is not None:
            signals.append(
                self._build_signal(
                    market, buy_a, close_last, dt,
                    bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b,
                    cci_val, volume_ratio, bb_width_quantile=None,
                    mode=StrategyMode.MEAN_REVERSION,
                )
            )

        sell_a = self._check_sell(close_last, bb_upper, cci_val, volume_ratio)
        if sell_a is not None:
            signals.append(
                self._build_signal(
                    market, sell_a, close_last, dt,
                    bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b,
                    cci_val, volume_ratio, bb_width_quantile=None,
                    mode=StrategyMode.MEAN_REVERSION,
                )
            )

        # ── 모드 B: 스퀴즈 돌파 (충분한 데이터 있을 때만) ─────────────────────
        min_len_b = self.squeeze_lookback + self.volume_lookback
        if len(candles) >= min_len_b:
            bb_widths = bb_df["bb_width"]
            recent = bb_widths.iloc[-self.squeeze_lookback :]
            sq_thresh = float(recent.quantile(self.squeeze_quantile))
            is_squeeze = bb_width <= sq_thresh
            bb_width_quantile = float(recent.rank(pct=True).iloc[-1])

            buy_b = self._check_squeeze_buy(
                close_last, bb_upper, cci_val, volume_ratio,
                is_squeeze, bb_width, recent,
            )
            if buy_b is not None:
                signals.append(
                    self._build_signal(
                        market, buy_b, close_last, dt,
                        bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b,
                        cci_val, volume_ratio,
                        bb_width_quantile=bb_width_quantile,
                        mode=StrategyMode.SQUEEZE_BREAKOUT,
                    )
                )

            sell_b = self._check_squeeze_sell(
                close_last, bb_lower, cci_val, volume_ratio,
                is_squeeze, bb_width, recent,
            )
            if sell_b is not None:
                signals.append(
                    self._build_signal(
                        market, sell_b, close_last, dt,
                        bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b,
                        cci_val, volume_ratio,
                        bb_width_quantile=bb_width_quantile,
                        mode=StrategyMode.SQUEEZE_BREAKOUT,
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

    def _check_squeeze_buy(
        self,
        close: float,
        bb_upper: float,
        cci_val: float,
        volume_ratio: float,
        is_squeeze: bool,
        bb_width: float,
        recent_widths: pd.Series,  # type: ignore[type-arg]
    ) -> tuple[SignalDirection, SignalStrength] | None:
        if not (
            is_squeeze
            and close > bb_upper
            and cci_val > self.cci_threshold_normal
            and volume_ratio >= self.volume_ratio_min_b
        ):
            return None
        q10 = float(recent_widths.quantile(0.10))
        strength = (
            SignalStrength.STRONG
            if volume_ratio >= 2.5 or bb_width <= q10
            else SignalStrength.NORMAL
        )
        return (SignalDirection.BUY, strength)

    def _check_squeeze_sell(
        self,
        close: float,
        bb_lower: float,
        cci_val: float,
        volume_ratio: float,
        is_squeeze: bool,
        bb_width: float,
        recent_widths: pd.Series,  # type: ignore[type-arg]
    ) -> tuple[SignalDirection, SignalStrength] | None:
        if not (
            is_squeeze
            and close < bb_lower
            and cci_val < -self.cci_threshold_normal
            and volume_ratio >= self.volume_ratio_min_b
        ):
            return None
        q10 = float(recent_widths.quantile(0.10))
        strength = (
            SignalStrength.STRONG
            if volume_ratio >= 2.5 or bb_width <= q10
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
        bb_width_quantile: float | None,
        mode: StrategyMode,
    ) -> Signal:
        direction, strength = direction_strength
        dt: datetime = triggered_at  # type: ignore[assignment]

        return Signal(
            market=market,
            timeframe=Timeframe.HOUR_1,
            mode=mode,
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
                bb_width_quantile=bb_width_quantile,
            ),
        )
