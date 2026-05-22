"""FourIndicatorStrategy (V2) — TDD RED → GREEN.

ADR-0010:
  score_total = 0.20*BB + 0.20*CCI + 0.20*Sto + 0.40*OBV >= buy_threshold(0.65)

Score 공식 (매수 기준):
  BB  : clip(1 - (close - bb_lower) / (bb_middle - bb_lower), 0, 1)
  CCI : clip(-cci / 200, 0, 1)
  Sto : clip(1 - stoch_k / sto_oversold, 0, 1)
  OBV : buy_score from compute_obv (abs() 분모 수정 포함)

매도는 대칭.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode
from signal_program.models import Signal
from signal_program.strategies.v2_4indicator import FourIndicatorStrategy

KST = timezone(timedelta(hours=9))


# ─── 테스트용 Settings 스텁 ──────────────────────────────────────────────────


@dataclass
class _Settings:
    """FourIndicatorStrategy 생성에 필요한 최소 Settings 스텁."""

    bb_period: int = 20
    bb_std_mult: float = 2.0
    cci_period: int = 20
    obv_lookback: int = 20
    sto_oversold: int = 15
    sto_overbought: int = 85
    bb_weight: float = 0.20
    cci_weight: float = 0.20
    sto_weight: float = 0.20
    obv_weight: float = 0.40
    buy_threshold: float = 0.65
    sell_threshold: float = 0.65


def _default_settings(**kwargs: object) -> _Settings:
    return _Settings(**kwargs)  # type: ignore[arg-type]


# ─── 캔들 생성 헬퍼 ──────────────────────────────────────────────────────────


def make_candles(
    closes: list[float],
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    market: str = "KRW-BTC",
) -> pd.DataFrame:
    if volumes is None:
        volumes = [1.0] * len(closes)
    if highs is None:
        highs = [c * 1.005 for c in closes]
    if lows is None:
        lows = [c * 0.995 for c in closes]
    base = datetime(2026, 1, 1, tzinfo=KST)
    rows = [
        {
            "market": market,
            "opened_at": base + timedelta(hours=i),
            "open": c,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "quote_volume": c * v,
        }
        for i, (c, h, l, v) in enumerate(zip(closes, highs, lows, volumes))
    ]
    return pd.DataFrame(rows)


def make_oscillating_candles(n: int, base: float = 10_000.0, amp: float = 300.0) -> pd.DataFrame:
    closes = [base + amp * math.sin(i * 0.4) for i in range(n)]
    return make_candles(closes)


MIN_CANDLES = 40


# ─── 스코어 함수 단위 테스트 ─────────────────────────────────────────────────


class TestScoreFunctions:
    def setup_method(self) -> None:
        self.strat = FourIndicatorStrategy(_default_settings())

    # BB 매수
    def test_score_bb_buy_at_lower_band(self) -> None:
        assert self.strat._score_bb_buy(100.0, bb_lower=100.0, bb_middle=105.0) == pytest.approx(1.0)

    def test_score_bb_buy_at_middle(self) -> None:
        assert self.strat._score_bb_buy(105.0, bb_lower=100.0, bb_middle=105.0) == pytest.approx(0.0)

    def test_score_bb_buy_below_lower(self) -> None:
        assert self.strat._score_bb_buy(95.0, bb_lower=100.0, bb_middle=105.0) == pytest.approx(1.0)

    def test_score_bb_buy_range(self) -> None:
        for close in [90.0, 100.0, 102.0, 105.0, 110.0]:
            s = self.strat._score_bb_buy(close, bb_lower=100.0, bb_middle=105.0)
            assert 0.0 <= s <= 1.0, f"close={close}: score={s}"

    # BB 매도
    def test_score_bb_sell_at_upper_band(self) -> None:
        assert self.strat._score_bb_sell(110.0, bb_upper=110.0, bb_middle=105.0) == pytest.approx(1.0)

    def test_score_bb_sell_at_middle(self) -> None:
        assert self.strat._score_bb_sell(105.0, bb_upper=110.0, bb_middle=105.0) == pytest.approx(0.0)

    def test_score_bb_sell_range(self) -> None:
        for close in [100.0, 105.0, 107.0, 110.0, 115.0]:
            s = self.strat._score_bb_sell(close, bb_upper=110.0, bb_middle=105.0)
            assert 0.0 <= s <= 1.0

    # CCI 매수
    def test_score_cci_buy_minus_200(self) -> None:
        assert self.strat._score_cci_buy(-200.0) == pytest.approx(1.0)

    def test_score_cci_buy_zero(self) -> None:
        assert self.strat._score_cci_buy(0.0) == pytest.approx(0.0)

    def test_score_cci_buy_positive(self) -> None:
        assert self.strat._score_cci_buy(100.0) == pytest.approx(0.0)

    def test_score_cci_buy_range(self) -> None:
        for v in [-300.0, -200.0, -100.0, 0.0, 100.0]:
            assert 0.0 <= self.strat._score_cci_buy(v) <= 1.0

    # CCI 매도
    def test_score_cci_sell_plus_200(self) -> None:
        assert self.strat._score_cci_sell(200.0) == pytest.approx(1.0)

    def test_score_cci_sell_negative(self) -> None:
        assert self.strat._score_cci_sell(-100.0) == pytest.approx(0.0)

    # Sto 매수 (sto_oversold=15)
    def test_score_sto_buy_zero_k(self) -> None:
        assert self.strat._score_sto_buy(0.0, sto_oversold=15) == pytest.approx(1.0)

    def test_score_sto_buy_at_threshold(self) -> None:
        assert self.strat._score_sto_buy(15.0, sto_oversold=15) == pytest.approx(0.0)

    def test_score_sto_buy_above_threshold(self) -> None:
        assert self.strat._score_sto_buy(50.0, sto_oversold=15) == pytest.approx(0.0)

    # Sto 매도 (sto_overbought=85)
    def test_score_sto_sell_at_100(self) -> None:
        assert self.strat._score_sto_sell(100.0, sto_overbought=85) == pytest.approx(1.0)

    def test_score_sto_sell_at_overbought(self) -> None:
        assert self.strat._score_sto_sell(85.0, sto_overbought=85) == pytest.approx(0.0)

    def test_score_sto_sell_below_threshold(self) -> None:
        assert self.strat._score_sto_sell(50.0, sto_overbought=85) == pytest.approx(0.0)


# ─── evaluate() 통합 테스트 ──────────────────────────────────────────────────


class TestFourIndicatorEvaluate:
    def setup_method(self) -> None:
        self.strat = FourIndicatorStrategy(_default_settings())

    def test_returns_empty_when_insufficient_candles(self) -> None:
        candles = make_oscillating_candles(n=MIN_CANDLES - 1)
        assert self.strat.evaluate("KRW-BTC", candles) == []

    def test_no_exception_with_minimum_candles(self) -> None:
        candles = make_oscillating_candles(n=MIN_CANDLES)
        result = self.strat.evaluate("KRW-BTC", candles)
        assert isinstance(result, list)

    def test_signal_has_correct_mode(self) -> None:
        """V2 시그널은 StrategyMode.WEIGHTED_SCORE 모드여야 한다."""
        strat = FourIndicatorStrategy(_default_settings(buy_threshold=0.0, sell_threshold=0.0))
        candles = make_oscillating_candles(n=MIN_CANDLES + 10)
        for sig in strat.evaluate("KRW-BTC", candles):
            assert sig.mode == StrategyMode.WEIGHTED_SCORE

    def test_signal_has_v2_indicators_when_fired(self) -> None:
        """V2 시그널 IndicatorSnapshot에 stoch_k, stoch_d, obv가 있어야 한다."""
        strat = FourIndicatorStrategy(_default_settings(buy_threshold=0.0, sell_threshold=0.0))
        candles = make_oscillating_candles(n=MIN_CANDLES + 10)
        signals = strat.evaluate("KRW-BTC", candles)
        assert len(signals) > 0, "threshold=0.0이면 시그널이 있어야 함"
        for sig in signals:
            assert sig.indicators.stoch_k is not None
            assert sig.indicators.stoch_d is not None
            assert sig.indicators.obv is not None

    def test_signal_type(self) -> None:
        strat = FourIndicatorStrategy(_default_settings(buy_threshold=0.0, sell_threshold=0.0))
        candles = make_oscillating_candles(n=MIN_CANDLES + 5)
        for s in strat.evaluate("KRW-BTC", candles):
            assert isinstance(s, Signal)

    def test_market_field_matches(self) -> None:
        strat = FourIndicatorStrategy(_default_settings(buy_threshold=0.0, sell_threshold=0.0))
        candles = make_oscillating_candles(n=MIN_CANDLES + 5)
        for sig in strat.evaluate("KRW-ETH", candles):
            assert sig.market == "KRW-ETH"


# ─── 임계값 경계 테스트 ──────────────────────────────────────────────────────


class TestThresholdBehavior:
    def test_high_threshold_suppresses_buy(self) -> None:
        strat = FourIndicatorStrategy(_default_settings(buy_threshold=1.0))
        candles = make_oscillating_candles(n=MIN_CANDLES + 10)
        buys = [s for s in strat.evaluate("KRW-BTC", candles) if s.direction == SignalDirection.BUY]
        assert buys == [], "threshold=1.0이면 매수 시그널 없어야 함"

    def test_zero_threshold_fires_signal(self) -> None:
        strat = FourIndicatorStrategy(_default_settings(buy_threshold=0.0, sell_threshold=0.0))
        candles = make_oscillating_candles(n=MIN_CANDLES + 10)
        assert len(strat.evaluate("KRW-BTC", candles)) > 0


# ─── 시그널 강도 ─────────────────────────────────────────────────────────────


class TestSignalStrength:
    def test_strength_is_valid(self) -> None:
        strat = FourIndicatorStrategy(_default_settings(buy_threshold=0.0, sell_threshold=0.0))
        candles = make_oscillating_candles(n=MIN_CANDLES + 5)
        for sig in strat.evaluate("KRW-BTC", candles):
            assert sig.strength in (SignalStrength.NORMAL, SignalStrength.STRONG)


# ─── STRATEGY_CATALOG / get_strategy 테스트 ──────────────────────────────────


class TestStrategyCatalog:
    def test_get_strategy_v1_returns_bbcci(self) -> None:
        from signal_program.config import Settings
        from signal_program.strategies import get_strategy
        from signal_program.strategies.bb_cci import BbCciStrategy

        assert isinstance(get_strategy("v1", Settings()), BbCciStrategy)

    def test_get_strategy_v2_returns_four_indicator(self) -> None:
        from signal_program.config import Settings
        from signal_program.strategies import get_strategy

        assert isinstance(get_strategy("v2", Settings()), FourIndicatorStrategy)

    def test_get_strategy_unknown_raises_value_error(self) -> None:
        from signal_program.config import Settings
        from signal_program.strategies import get_strategy

        with pytest.raises(ValueError, match="전략 버전"):
            get_strategy("v99", Settings())

    def test_catalog_keys(self) -> None:
        from signal_program.strategies import STRATEGY_CATALOG

        assert "v1" in STRATEGY_CATALOG
        assert "v2" in STRATEGY_CATALOG
