"""BbCciStrategy regime_filter (ADR-0024 Risks 후속 실험) — TDD RED → GREEN.

레짐 필터는 매수(BUY) 시그널만 게이트한다. SELL은 필터 무관 항상 발생 (보유자 보호).
"""

from __future__ import annotations

import math

import pandas as pd

from signal_program.enums import SignalDirection
from signal_program.models import Signal
from signal_program.strategies.bb_cci import BbCciStrategy


def make_candles(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    """합성 캔들 DataFrame. high=close*1.005, low=close*0.995."""
    if volumes is None:
        volumes = [1.0] * len(closes)
    base = pd.Timestamp("2026-01-01", tz="Asia/Seoul")
    rows = [
        {
            "market": "005930",
            "opened_at": base + pd.Timedelta(days=i),
            "open": c,
            "high": c * 1.005,
            "low": c * 0.995,
            "close": c,
            "volume": v,
            "quote_volume": c * v,
        }
        for i, (c, v) in enumerate(zip(closes, volumes, strict=False))
    ]
    return pd.DataFrame(rows)


def _oscillating_tail(n: int = 60, amplitude: float = 200.0, base: float = 10_000.0) -> list[float]:
    return [base + amplitude * math.sin(i * 0.4) for i in range(n)]


REGIME_PERIOD = 100  # 테스트 전용 축소값 (기본 200과 별개, 파라미터화 검증)


def _buy_scenario(baseline: float, n_baseline: int, close_last: float = 9600.0) -> pd.DataFrame:
    """n_baseline개 평평한 baseline + 60봉 oscillating tail(마지막 봉이 BUY 조건)."""
    tail = _oscillating_tail(60)
    tail[-1] = close_last
    closes = [baseline] * n_baseline + tail
    volumes = [1.0] * len(closes)
    volumes[-1] = 1.2 * (sum(volumes[-21:-1]) / 20)
    return make_candles(closes, volumes)


def _sell_scenario(baseline: float, n_baseline: int, close_last: float = 10_400.0) -> pd.DataFrame:
    """n_baseline개 평평한 baseline + 60봉 oscillating tail(마지막 봉이 SELL 조건)."""
    tail = _oscillating_tail(60)
    tail[-1] = close_last
    closes = [baseline] * n_baseline + tail
    volumes = [1.0] * len(closes)
    volumes[-1] = 1.2 * (sum(volumes[-21:-1]) / 20)
    return make_candles(closes, volumes)


def _buy_signals(result: list[Signal]) -> list[Signal]:
    return [s for s in result if s.direction == SignalDirection.BUY]


def _sell_signals(result: list[Signal]) -> list[Signal]:
    return [s for s in result if s.direction == SignalDirection.SELL]


# ─── 1) regime_filter=None → 기존 v1과 완전 동일 (회귀 없음) ────────────────


def test_regime_filter_none_matches_default_behavior() -> None:
    candles = _buy_scenario(baseline=8_000.0, n_baseline=40)
    default_strat = BbCciStrategy()
    explicit_none_strat = BbCciStrategy(regime_filter=None)
    assert default_strat.evaluate("005930", candles) == explicit_none_strat.evaluate(
        "005930", candles
    )
    assert len(_buy_signals(default_strat.evaluate("005930", candles))) == 1


# ─── 2) above_sma: close_last > sma → 매수 허용 / close_last < sma → 매수 억제 ──


def test_above_sma_allows_buy_when_close_above_sma() -> None:
    # baseline=8000 낮게 깔아 sma(100)를 close_last(9600) 아래로 유도
    candles = _buy_scenario(baseline=8_000.0, n_baseline=40)
    strat = BbCciStrategy(regime_filter="above_sma", regime_sma_period=REGIME_PERIOD)
    assert len(_buy_signals(strat.evaluate("005930", candles))) == 1


def test_above_sma_suppresses_buy_when_close_below_sma() -> None:
    # baseline=12000 높게 깔아 sma(100)를 close_last(9600) 위로 유도
    candles = _buy_scenario(baseline=12_000.0, n_baseline=40)
    strat = BbCciStrategy(regime_filter="above_sma", regime_sma_period=REGIME_PERIOD)
    assert _buy_signals(strat.evaluate("005930", candles)) == []


def test_above_sma_sell_fires_regardless() -> None:
    for baseline in (8_000.0, 12_000.0):
        candles = _sell_scenario(baseline=baseline, n_baseline=40)
        strat = BbCciStrategy(regime_filter="above_sma", regime_sma_period=REGIME_PERIOD)
        assert len(_sell_signals(strat.evaluate("005930", candles))) == 1


# ─── 3) below_sma: 2의 반대 ──────────────────────────────────────────────────


def test_below_sma_allows_buy_when_close_below_sma() -> None:
    candles = _buy_scenario(baseline=12_000.0, n_baseline=40)
    strat = BbCciStrategy(regime_filter="below_sma", regime_sma_period=REGIME_PERIOD)
    assert len(_buy_signals(strat.evaluate("005930", candles))) == 1


def test_below_sma_suppresses_buy_when_close_above_sma() -> None:
    candles = _buy_scenario(baseline=8_000.0, n_baseline=40)
    strat = BbCciStrategy(regime_filter="below_sma", regime_sma_period=REGIME_PERIOD)
    assert _buy_signals(strat.evaluate("005930", candles)) == []


def test_below_sma_sell_fires_regardless() -> None:
    for baseline in (8_000.0, 12_000.0):
        candles = _sell_scenario(baseline=baseline, n_baseline=40)
        strat = BbCciStrategy(regime_filter="below_sma", regime_sma_period=REGIME_PERIOD)
        assert len(_sell_signals(strat.evaluate("005930", candles))) == 1


# ─── 4) len(candles) < regime_sma_period → 매수 억제, SELL 유지 ─────────────


def test_insufficient_history_suppresses_buy_but_keeps_sell() -> None:
    buy_candles = _buy_scenario(baseline=8_000.0, n_baseline=0)  # 60봉 < 기본 200
    sell_candles = _sell_scenario(baseline=8_000.0, n_baseline=0)
    for regime in ("above_sma", "below_sma"):
        strat = BbCciStrategy(regime_filter=regime)  # regime_sma_period 기본값 200
        assert _buy_signals(strat.evaluate("005930", buy_candles)) == []
        assert len(_sell_signals(strat.evaluate("005930", sell_candles))) == 1


# ─── 5) Strategy Protocol 계속 만족 ──────────────────────────────────────────


def test_still_satisfies_strategy_protocol() -> None:
    strat = BbCciStrategy(regime_filter="above_sma")
    assert isinstance(strat.name, str)
    candles = _buy_scenario(baseline=8_000.0, n_baseline=40)
    result = strat.evaluate("005930", candles)
    assert isinstance(result, list)
    for sig in result:
        assert isinstance(sig, Signal)
