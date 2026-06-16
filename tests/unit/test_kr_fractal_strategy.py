"""KrFractalStrategy — Williams Fractal Breakout 전략 단위 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode
from signal_program.strategies.kr_fractal import KrFractalStrategy, _find_fractals, _infer_timeframe

KST = timezone(timedelta(hours=9))


def _make_candles(
    n: int = 30,
    base_price: float = 10000.0,
    volume: float = 1.0,
    interval_hours: int = 1,
) -> pd.DataFrame:
    """균등한 합성 캔들 DataFrame."""
    base = datetime(2026, 1, 1, 9, 0, tzinfo=KST)
    rows = []
    for i in range(n):
        rows.append(
            {
                "market": "005930",
                "opened_at": base + timedelta(hours=i * interval_hours),
                "open": base_price,
                "high": base_price * 1.005,
                "low": base_price * 0.995,
                "close": base_price,
                "volume": volume,
                "quote_volume": base_price * volume,
            }
        )
    return pd.DataFrame(rows)


def _inject_fractal_up(df: pd.DataFrame, idx: int, high_val: float) -> pd.DataFrame:
    """idx 위치에 Up Fractal을 만든다 (high[idx] > 양쪽 2개)."""
    df = df.copy()
    df.at[idx, "high"] = high_val
    df.at[idx, "close"] = high_val
    for i in [idx - 2, idx - 1, idx + 1, idx + 2]:
        if 0 <= i < len(df):
            df.at[i, "high"] = high_val * 0.99
    return df


def _inject_fractal_down(df: pd.DataFrame, idx: int, low_val: float) -> pd.DataFrame:
    """idx 위치에 Down Fractal을 만든다 (low[idx] < 양쪽 2개)."""
    df = df.copy()
    df.at[idx, "low"] = low_val
    df.at[idx, "close"] = low_val
    for i in [idx - 2, idx - 1, idx + 1, idx + 2]:
        if 0 <= i < len(df):
            df.at[i, "low"] = low_val * 1.01
    return df


# ---------------------------------------------------------------------------
# _infer_timeframe
# ---------------------------------------------------------------------------


def test_infer_timeframe_60m() -> None:
    df = _make_candles(10, interval_hours=1)
    assert _infer_timeframe(df).value == "60"


def test_infer_timeframe_120m() -> None:
    df = _make_candles(10, interval_hours=2)
    assert _infer_timeframe(df).value == "120"


def test_infer_timeframe_single_candle_defaults_to_60m() -> None:
    df = _make_candles(1)
    assert _infer_timeframe(df).value == "60"


def test_infer_timeframe_day() -> None:
    """24시간 간격 캔들은 DAY(1440)로 추론된다."""
    df = _make_candles(10, interval_hours=24)
    assert _infer_timeframe(df).value == "1440"


def test_infer_timeframe_day_weekend_gap() -> None:
    """금→월 72시간 간격도 DAY로 추론된다."""
    df = _make_candles(10, interval_hours=72)
    assert _infer_timeframe(df).value == "1440"


# ---------------------------------------------------------------------------
# _find_fractals
# ---------------------------------------------------------------------------


def test_find_fractals_finds_up_fractal() -> None:
    df = _make_candles(30)
    idx = 25
    df = _inject_fractal_up(df, idx, high_val=11000.0)
    up_level, up_age, down_level, down_age = _find_fractals(df, lookback=100)
    assert up_level == pytest.approx(11000.0)
    assert up_age == len(df) - 1 - idx


def test_find_fractals_finds_down_fractal() -> None:
    df = _make_candles(30)
    idx = 24
    df = _inject_fractal_down(df, idx, low_val=9000.0)
    up_level, up_age, down_level, down_age = _find_fractals(df, lookback=100)
    assert down_level == pytest.approx(9000.0)


def test_find_fractals_returns_none_when_no_fractal() -> None:
    df = _make_candles(30)
    up_level, _, down_level, _ = _find_fractals(df, lookback=100)
    assert up_level is None
    assert down_level is None


# ---------------------------------------------------------------------------
# KrFractalStrategy.evaluate
# ---------------------------------------------------------------------------


def test_evaluate_returns_empty_when_too_few_candles() -> None:
    strat = KrFractalStrategy()
    df = _make_candles(5)
    assert strat.evaluate("005930", df) == []


def test_evaluate_no_signal_when_volume_below_threshold() -> None:
    strat = KrFractalStrategy(fractal_volume_threshold=1.5)
    df = _make_candles(30, volume=1.0)
    assert strat.evaluate("005930", df) == []


def test_evaluate_buy_signal_on_fractal_up_breakout() -> None:
    strat = KrFractalStrategy(
        fractal_volume_threshold=1.2,
        fractal_volume_strong=2.0,
        volume_lookback=20,
    )
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    fractal_idx = 27
    df = _inject_fractal_up(df, fractal_idx, high_val=9500.0)
    df.at[len(df) - 1, "volume"] = 1.5
    df.at[len(df) - 1, "close"] = 10000.0

    signals = strat.evaluate("005930", df)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.direction == SignalDirection.BUY
    assert sig.mode == StrategyMode.FRACTAL_BREAKOUT
    assert sig.indicators.fractal_up == pytest.approx(9500.0)


def test_evaluate_sell_signal_on_fractal_down_breakout() -> None:
    strat = KrFractalStrategy(
        fractal_volume_threshold=1.2,
        fractal_volume_strong=2.0,
        volume_lookback=20,
    )
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    fractal_idx = 26
    df = _inject_fractal_down(df, fractal_idx, low_val=10500.0)
    df.at[len(df) - 1, "volume"] = 1.5
    df.at[len(df) - 1, "close"] = 10000.0

    signals = strat.evaluate("005930", df)
    assert len(signals) == 1
    assert signals[0].direction == SignalDirection.SELL
    assert signals[0].mode == StrategyMode.FRACTAL_BREAKOUT


def test_evaluate_strong_signal_when_volume_exceeds_strong_threshold() -> None:
    strat = KrFractalStrategy(
        fractal_volume_threshold=1.2,
        fractal_volume_strong=2.0,
        volume_lookback=20,
    )
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    fractal_idx = 27
    df = _inject_fractal_up(df, fractal_idx, high_val=9500.0)
    df.at[len(df) - 1, "volume"] = 2.5
    df.at[len(df) - 1, "close"] = 10000.0

    signals = strat.evaluate("005930", df)
    assert len(signals) == 1
    assert signals[0].strength == SignalStrength.STRONG


def test_evaluate_normal_signal_when_volume_below_strong_threshold() -> None:
    strat = KrFractalStrategy(
        fractal_volume_threshold=1.2,
        fractal_volume_strong=2.0,
        volume_lookback=20,
    )
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    fractal_idx = 27
    df = _inject_fractal_up(df, fractal_idx, high_val=9500.0)
    df.at[len(df) - 1, "volume"] = 1.3
    df.at[len(df) - 1, "close"] = 10000.0

    signals = strat.evaluate("005930", df)
    assert len(signals) == 1
    assert signals[0].strength == SignalStrength.NORMAL


def test_signal_fractal_fields_set_correctly() -> None:
    strat = KrFractalStrategy(fractal_volume_threshold=1.2, volume_lookback=20)
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    fractal_idx = 27
    df = _inject_fractal_up(df, fractal_idx, high_val=9500.0)
    df.at[len(df) - 1, "volume"] = 1.5
    df.at[len(df) - 1, "close"] = 10000.0

    signals = strat.evaluate("005930", df)
    assert signals
    ind = signals[0].indicators
    assert ind.fractal_up == pytest.approx(9500.0)
    assert ind.fractal_up_age is not None and ind.fractal_up_age > 0
    assert ind.volume_ratio == pytest.approx(1.5, rel=0.1)
    assert ind.bb_upper == 0.0


def test_signal_market_and_mode() -> None:
    strat = KrFractalStrategy(fractal_volume_threshold=1.2, volume_lookback=20)
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    fractal_idx = 27
    df = _inject_fractal_up(df, fractal_idx, high_val=9500.0)
    df.at[len(df) - 1, "volume"] = 1.5
    df.at[len(df) - 1, "close"] = 10000.0

    signals = strat.evaluate("005930", df)
    assert signals[0].market == "005930"
    assert signals[0].mode == StrategyMode.FRACTAL_BREAKOUT


def test_strategy_name() -> None:
    assert KrFractalStrategy.name == "kr_fractal_v1"
