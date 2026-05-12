"""BbCciStrategy 모드 A — TDD RED → GREEN 시나리오 13종 + Hypothesis property."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode
from signal_program.models import Signal
from signal_program.strategies.bb_cci import BbCciStrategy

KST = timezone(timedelta(hours=9))


def make_candles(
    closes: list[float],
    volumes: list[float] | None = None,
    market: str = "KRW-BTC",
    start: str = "2026-01-01T00:00+09:00",
) -> pd.DataFrame:
    """합성 캔들 DataFrame. high=close*1.005, low=close*0.995."""
    if volumes is None:
        volumes = [1.0] * len(closes)
    base = datetime.fromisoformat(start)
    rows = [
        {
            "market": market,
            "opened_at": base + timedelta(hours=i),
            "open": c,
            "high": c * 1.005,
            "low": c * 0.995,
            "close": c,
            "volume": v,
            "quote_volume": c * v,
        }
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]
    return pd.DataFrame(rows)


def _oscillating_closes(n: int, amplitude: float = 200.0, base: float = 10_000.0) -> list[float]:
    """비-flat 기저로 BB/CCI 분산을 확보. 마지막 봉을 직접 교체 가능."""
    return [base + amplitude * math.sin(i * 0.4) for i in range(n)]


def _buy_candles(vol_ratio: float = 1.2, close_last: float = 9500.0) -> pd.DataFrame:
    """oscillating base + 지정 최종 close — BB 하단 이탈, CCI 음수 유도."""
    n = 60
    closes = _oscillating_closes(n)
    closes[-1] = close_last
    volumes = [1.0] * n
    volumes[-1] = vol_ratio * (sum(volumes[-21:-1]) / 20)
    return make_candles(closes, volumes)


def _sell_candles(vol_ratio: float = 1.2, close_last: float = 10_500.0) -> pd.DataFrame:
    """oscillating base + 지정 최종 close — BB 상단 이탈, CCI 양수 유도."""
    n = 60
    closes = _oscillating_closes(n)
    closes[-1] = close_last
    volumes = [1.0] * n
    volumes[-1] = vol_ratio * (sum(volumes[-21:-1]) / 20)
    return make_candles(closes, volumes)


STRAT = BbCciStrategy()


def _eval(candles: pd.DataFrame) -> list:
    return STRAT.evaluate("KRW-BTC", candles)


# ─── Probe 결과 (oscillating amp=200, base=10000, n=60):
#   close=9600 → bb_lower=9634, cci=-177  (NORMAL)
#   close=9500 → bb_lower=9603, cci=-217  (STRONG)
#   close=9950 → bb_lower=9698, cci=-15   (가격·CCI 모두 조건 미달)
#   close=10500 → bb_upper=10367, cci=+227 (SELL STRONG)
#   close=10400 → bb_upper=~10320, cci=~+177 (SELL NORMAL 근방)


# (a) BUY Normal — cci=-177, close=9600 < bb_lower=9634
def test_buy_normal() -> None:
    result = _eval(_buy_candles(vol_ratio=1.2, close_last=9600.0))
    assert len(result) == 1
    s = result[0]
    assert s.direction == SignalDirection.BUY
    assert s.strength == SignalStrength.NORMAL
    assert s.mode == StrategyMode.MEAN_REVERSION
    assert s.market == "KRW-BTC"
    assert s.triggered_at.tzinfo is not None


# (b) BUY Strong — cci=-217, close=9500 < bb_lower=9603
def test_buy_strong() -> None:
    result = _eval(_buy_candles(close_last=9500.0))
    assert len(result) == 1
    assert result[0].direction == SignalDirection.BUY
    assert result[0].strength == SignalStrength.STRONG


# (c) BUY 부정 — 가격·CCI 모두 조건 미달 (close=9950 > bb_lower, cci=-15)
def test_buy_negative_cci_and_price() -> None:
    candles = _buy_candles(close_last=9950.0)
    buy_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 0


# (d) BUY 부정 — 가격이 bb_lower 위 (flat → close == bb_middle)
def test_buy_negative_price_above_lower() -> None:
    candles = make_candles([10_000.0] * 60)
    buy_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 0


# (e) BUY 부정 — 거래량 미달 (vol_ratio=0.5 < 1.0)
def test_buy_negative_volume_low() -> None:
    candles = _buy_candles(vol_ratio=0.5, close_last=9600.0)
    buy_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 0


# (f) BUY 경계 — NORMAL 강도(cci=-177)
def test_buy_boundary_normal_strength() -> None:
    result = _eval(_buy_candles(vol_ratio=1.2, close_last=9600.0))
    buy_sigs = [s for s in result if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 1
    assert buy_sigs[0].strength == SignalStrength.NORMAL


# (g) BUY 경계 — STRONG 강도(cci=-217)
def test_buy_boundary_strong_strength() -> None:
    result = _eval(_buy_candles(close_last=9500.0))
    buy_sigs = [s for s in result if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 1
    assert buy_sigs[0].strength == SignalStrength.STRONG


# (h) SELL Normal — cci=+177, close=10400 > bb_upper
def test_sell_normal() -> None:
    result = _eval(_sell_candles(vol_ratio=1.2, close_last=10_400.0))
    assert len(result) == 1
    s = result[0]
    assert s.direction == SignalDirection.SELL
    assert s.strength == SignalStrength.NORMAL
    assert s.mode == StrategyMode.MEAN_REVERSION


# (i) SELL Strong — cci=+227, close=10500 > bb_upper
def test_sell_strong() -> None:
    result = _eval(_sell_candles(close_last=10_500.0))
    assert len(result) == 1
    assert result[0].direction == SignalDirection.SELL
    assert result[0].strength == SignalStrength.STRONG


# (j) SELL 부정 3종
def test_sell_negative_cci_and_price() -> None:
    candles = _sell_candles(close_last=10_050.0)
    sell_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 0


def test_sell_negative_price_below_upper() -> None:
    candles = make_candles([10_000.0] * 60)
    sell_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 0


def test_sell_negative_volume_low() -> None:
    candles = _sell_candles(vol_ratio=0.5, close_last=10_500.0)
    sell_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 0


# (k) SELL 경계 2종
def test_sell_boundary_normal_strength() -> None:
    result = _eval(_sell_candles(vol_ratio=1.2, close_last=10_400.0))
    sell_sigs = [s for s in result if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 1
    assert sell_sigs[0].strength == SignalStrength.NORMAL


def test_sell_boundary_strong_strength() -> None:
    result = _eval(_sell_candles(close_last=10_500.0))
    sell_sigs = [s for s in result if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 1
    assert sell_sigs[0].strength == SignalStrength.STRONG


# (l) 데이터 부족 → []
def test_insufficient_data_returns_empty() -> None:
    candles = make_candles([10_000.0] * 10)
    assert _eval(candles) == []


# (m) 박스권 → []
def test_sideways_no_signal() -> None:
    candles = make_candles([10_000.0] * 60)
    assert _eval(candles) == []


# ─── Phase 3: Hypothesis property 테스트 ────────────────────────────────────

@given(
    closes=st.lists(
        st.floats(min_value=100.0, max_value=100_000.0, allow_nan=False, allow_infinity=False),
        min_size=60,
        max_size=200,
    )
)
@settings(max_examples=100, deadline=2000)
def test_property_no_exception_on_positive_series(closes: list[float]) -> None:
    """임의 양수 시계열 → 예외 없이 list[Signal] 반환."""
    candles = make_candles(closes)
    result = _eval(candles)
    assert isinstance(result, list)
    for sig in result:
        assert isinstance(sig, Signal)


@given(
    closes=st.lists(
        st.floats(min_value=100.0, max_value=100_000.0, allow_nan=False, allow_infinity=False),
        min_size=60,
        max_size=200,
    ),
    threshold=st.integers(min_value=50, max_value=500),
)
@settings(max_examples=100, deadline=2000)
def test_property_varying_cci_threshold(closes: list[float], threshold: int) -> None:
    """임의 cci_threshold_normal → 예외 없이 반환, NaN 포함 없음."""
    strat = BbCciStrategy(cci_threshold_normal=threshold)
    candles = make_candles(closes)
    result = strat.evaluate("KRW-BTC", candles)
    assert isinstance(result, list)


@given(
    closes=st.lists(
        st.floats(min_value=100.0, max_value=100_000.0, allow_nan=False, allow_infinity=False),
        min_size=60,
        max_size=200,
    ),
    vol_min=st.floats(min_value=0.1, max_value=5.0, allow_nan=False),
)
@settings(max_examples=100, deadline=2000)
def test_property_varying_volume_ratio_min(closes: list[float], vol_min: float) -> None:
    """임의 volume_ratio_min_a → 예외 없이 반환."""
    strat = BbCciStrategy(volume_ratio_min_a=vol_min)
    candles = make_candles(closes)
    result = strat.evaluate("KRW-BTC", candles)
    assert isinstance(result, list)


# ─── Phase 3: 파라미터 보강 (parametrize) ────────────────────────────────────

@pytest.mark.parametrize("vol_min,expect_signal", [
    (0.5, True),   # 0.5 ≤ vol_ratio(1.2) → 시그널 발생
    (1.0, True),   # 1.0 ≤ 1.2 → 시그널 발생
    (1.5, False),  # 1.5 > 1.2 → 시그널 없음
    (2.0, False),  # 2.0 > 1.2 → 시그널 없음
])
def test_volume_ratio_min_controls_signal(vol_min: float, expect_signal: bool) -> None:
    """volume_ratio_min_a 변화에 따른 BUY 시그널 유무."""
    strat = BbCciStrategy(volume_ratio_min_a=vol_min)
    candles = _buy_candles(vol_ratio=1.2, close_last=9600.0)
    result = strat.evaluate("KRW-BTC", candles)
    buy_sigs = [s for s in result if s.direction == SignalDirection.BUY]
    assert bool(buy_sigs) == expect_signal


@pytest.mark.parametrize("strong_thresh,expected_strength", [
    (100, SignalStrength.STRONG),   # threshold=100, cci=-177 → STRONG
    (150, SignalStrength.STRONG),   # threshold=150, cci=-177 → STRONG
    (200, SignalStrength.NORMAL),   # threshold=200, cci=-177 < 200 → NORMAL
    (300, SignalStrength.NORMAL),   # threshold=300, cci=-177 < 300 → NORMAL
])
def test_cci_threshold_strong_controls_strength(
    strong_thresh: int, expected_strength: SignalStrength
) -> None:
    """cci_threshold_strong 변화에 따른 Strength 분기."""
    strat = BbCciStrategy(cci_threshold_strong=strong_thresh)
    candles = _buy_candles(vol_ratio=1.2, close_last=9600.0)
    result = strat.evaluate("KRW-BTC", candles)
    buy_sigs = [s for s in result if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 1
    assert buy_sigs[0].strength == expected_strength
