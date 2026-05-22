"""FourIndicatorStrategy — ADR-0010 V2 가중치 점수제 전략.

score_total = 0.20*BB + 0.20*CCI + 0.20*Sto + 0.40*OBV >= threshold(0.65 기본)

Score 공식 (매수 기준):
  BB  : clip(1 - (close - bb_lower) / (bb_middle - bb_lower), 0, 1)
  CCI : clip(-cci / 200, 0, 1)
  Sto : clip(1 - stoch_k / sto_oversold, 0, 1)   — sto_oversold=15 엄격
  OBV : buy_score from compute_obv(abs() 분모, ADR-0010 리스크 #1 수정)

매도는 대칭.
StrategyMode: WEIGHTED_SCORE ("C")
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

if TYPE_CHECKING:
    from datetime import datetime

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.indicators.bollinger import bollinger
from signal_program.indicators.cci import cci
from signal_program.indicators.obv import compute_obv
from signal_program.indicators.stochastic import compute_stochastic_slow
from signal_program.models import IndicatorSnapshot, Signal

_KST = ZoneInfo("Asia/Seoul")


class FourIndicatorStrategy:
    """4지표 가중치 점수제 전략 (V2).

    Parameters
    ----------
    settings:
        config.Settings 인스턴스 또는 동일한 속성을 가진 객체.
        필수 속성: bb_period, bb_std_mult, cci_period, obv_lookback,
                   bb_weight, cci_weight, sto_weight, obv_weight,
                   buy_threshold, sell_threshold, sto_oversold, sto_overbought.
    """

    name = "v2_4indicator"

    def __init__(self, settings: object) -> None:
        self.bb_period: int = getattr(settings, "bb_period", 20)
        self.bb_std_mult: float = getattr(settings, "bb_std_mult", 2.0)
        self.cci_period: int = getattr(settings, "cci_period", 20)
        self.obv_lookback: int = getattr(settings, "obv_lookback", 20)
        self.sto_k: int = 14  # Stochastic Fast %K 기간 (고정, ADR-0010)
        self.sto_d: int = 3  # Stochastic 평활 기간 (고정, ADR-0010)
        self.sto_oversold: int = getattr(settings, "sto_oversold", 15)
        self.sto_overbought: int = getattr(settings, "sto_overbought", 85)
        self.bb_weight: float = getattr(settings, "bb_weight", 0.20)
        self.cci_weight: float = getattr(settings, "cci_weight", 0.20)
        self.sto_weight: float = getattr(settings, "sto_weight", 0.20)
        self.obv_weight: float = getattr(settings, "obv_weight", 0.40)
        self.buy_threshold: float = getattr(settings, "buy_threshold", 0.65)
        self.sell_threshold: float = getattr(settings, "sell_threshold", 0.65)

    # ── 공개 메서드 ────────────────────────────────────────────────────────

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]:
        """캔들 DataFrame → 시그널 목록.

        최소 캔들 수 미달 시 빈 리스트 반환.
        """
        # 최소 캔들 수: 지표별 최대 lookback + 거래량 비율 lookback
        volume_lookback = self.obv_lookback
        min_stoch = self.sto_k + 2 * self.sto_d - 3  # stoch_d 유효값 시작
        min_len = max(self.bb_period, self.cci_period, min_stoch) + volume_lookback
        if len(candles) < min_len:
            return []

        close = candles["close"]
        high = candles["high"]
        low = candles["low"]
        volume = candles["volume"]

        # ── 지표 계산 ──────────────────────────────────────────────────────
        bb_df = bollinger(close, self.bb_period, self.bb_std_mult)
        cci_series = cci(high, low, close, self.cci_period)
        stoch_df = compute_stochastic_slow(candles, k=self.sto_k, d=self.sto_d)
        obv_df = compute_obv(candles, lookback=self.obv_lookback)

        # 최종 봉 값 추출
        bb_upper = float(bb_df["bb_upper"].iloc[-1])
        bb_middle = float(bb_df["bb_middle"].iloc[-1])
        bb_lower = float(bb_df["bb_lower"].iloc[-1])
        bb_width = float(bb_df["bb_width"].iloc[-1])
        bb_pct_b = float(bb_df["bb_pct_b"].iloc[-1])
        cci_val = float(cci_series.iloc[-1])
        stoch_k_val = float(stoch_df["stoch_k"].iloc[-1])
        stoch_d_val = float(stoch_df["stoch_d"].iloc[-1])
        obv_raw = float(obv_df["obv"].iloc[-1])
        obv_buy = float(obv_df["buy_score"].iloc[-1])
        obv_sell = float(obv_df["sell_score"].iloc[-1])
        close_last = float(close.iloc[-1])

        # 거래량 비율 (참고용 — V2 scoring에는 미사용)
        vol_mean = float(volume.iloc[-self.obv_lookback - 1 : -1].mean())
        volume_ratio = float(volume.iloc[-1]) / vol_mean if vol_mean > 0 else 0.0

        # 타임스탬프
        raw_ts = candles["opened_at"].iloc[-1]
        dt: datetime = raw_ts.to_pydatetime() if isinstance(raw_ts, pd.Timestamp) else raw_ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)

        # 유효성 검사 (NaN 지표 있으면 skip)
        import math as _math

        if any(
            _math.isnan(v)
            for v in [bb_upper, bb_middle, bb_lower, cci_val, stoch_k_val, stoch_d_val, obv_buy]
        ):
            return []

        indicators = IndicatorSnapshot(
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            bb_width=bb_width,
            bb_pct_b=bb_pct_b,
            cci=cci_val,
            volume_ratio=volume_ratio,
            bb_width_quantile=None,
            stoch_k=stoch_k_val,
            stoch_d=stoch_d_val,
            obv=obv_raw,
        )

        signals: list[Signal] = []

        # ── 매수 판정 ──────────────────────────────────────────────────────
        buy_score = (
            self.bb_weight * self._score_bb_buy(close_last, bb_lower, bb_middle)
            + self.cci_weight * self._score_cci_buy(cci_val)
            + self.sto_weight * self._score_sto_buy(stoch_k_val, self.sto_oversold)
            + self.obv_weight * obv_buy
        )
        if buy_score >= self.buy_threshold:
            signals.append(
                self._build_signal(
                    market, SignalDirection.BUY, buy_score, close_last, dt, indicators
                )
            )

        # ── 매도 판정 ──────────────────────────────────────────────────────
        sell_score = (
            self.bb_weight * self._score_bb_sell(close_last, bb_upper, bb_middle)
            + self.cci_weight * self._score_cci_sell(cci_val)
            + self.sto_weight * self._score_sto_sell(stoch_k_val, self.sto_overbought)
            + self.obv_weight * obv_sell
        )
        if sell_score >= self.sell_threshold:
            signals.append(
                self._build_signal(
                    market, SignalDirection.SELL, sell_score, close_last, dt, indicators
                )
            )

        return signals

    # ── 스코어 함수 (정적 메서드, 직접 테스트 가능) ────────────────────────

    @staticmethod
    def _score_bb_buy(close: float, bb_lower: float, bb_middle: float) -> float:
        """BB 매수 스코어: 하단 터치 = 1.0, 중앙선 = 0.0."""
        denom = bb_middle - bb_lower
        if denom <= 0:
            return 0.0
        return min(1.0, max(0.0, 1.0 - (close - bb_lower) / denom))

    @staticmethod
    def _score_bb_sell(close: float, bb_upper: float, bb_middle: float) -> float:
        """BB 매도 스코어: 상단 터치 = 1.0, 중앙선 = 0.0."""
        denom = bb_upper - bb_middle
        if denom <= 0:
            return 0.0
        return min(1.0, max(0.0, 1.0 - (bb_upper - close) / denom))

    @staticmethod
    def _score_cci_buy(cci_val: float) -> float:
        """CCI 매수 스코어: CCI=-200 = 1.0, 0 = 0.0."""
        return min(1.0, max(0.0, -cci_val / 200.0))

    @staticmethod
    def _score_cci_sell(cci_val: float) -> float:
        """CCI 매도 스코어: CCI=+200 = 1.0, 0 = 0.0."""
        return min(1.0, max(0.0, cci_val / 200.0))

    @staticmethod
    def _score_sto_buy(stoch_k: float, sto_oversold: float) -> float:
        """Sto 매수 스코어: %K=0 = 1.0, %K=sto_oversold = 0.0."""
        if sto_oversold <= 0:
            return 0.0
        return min(1.0, max(0.0, 1.0 - stoch_k / sto_oversold))

    @staticmethod
    def _score_sto_sell(stoch_k: float, sto_overbought: float) -> float:
        """Sto 매도 스코어: %K=100 = 1.0, %K=sto_overbought = 0.0."""
        range_ = 100.0 - sto_overbought
        if range_ <= 0:
            return 0.0
        return min(1.0, max(0.0, (stoch_k - sto_overbought) / range_))

    # ── 시그널 조립 ────────────────────────────────────────────────────────

    def _build_signal(
        self,
        market: str,
        direction: SignalDirection,
        score: float,
        price: float,
        triggered_at: object,
        indicators: IndicatorSnapshot,
    ) -> Signal:
        dt: datetime = triggered_at  # type: ignore[assignment]
        # 강도: threshold + 0.15 이상이면 STRONG
        threshold = self.buy_threshold if direction == SignalDirection.BUY else self.sell_threshold
        strength = SignalStrength.STRONG if score >= threshold + 0.15 else SignalStrength.NORMAL
        return Signal(
            market=market,
            timeframe=Timeframe.HOUR_1,
            mode=StrategyMode.WEIGHTED_SCORE,
            direction=direction,
            strength=strength,
            price=price,
            triggered_at=dt,
            indicators=indicators,
        )
