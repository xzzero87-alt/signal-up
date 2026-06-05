"""FractalStrategy (암호화폐) — KrFractal 로직 일반화 (설계 v2.3 §3.1). TDD RED→GREEN.

회귀 보장: KRW 마켓 + 동일 패턴 입력 시 KrFractalStrategy와 동일 신호.
추가: fractal_max_age 필터, 거래량 필터, STRONG 경계. 국장 타임프레임 추론은 미사용(고정 1h).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.strategies.fractal import FractalStrategy
from signal_program.strategies.kr_fractal import KrFractalStrategy

KST = timezone(timedelta(hours=9))


def _make_candles(n: int = 30, base_price: float = 10000.0, volume: float = 1.0) -> pd.DataFrame:
    base = datetime(2026, 1, 1, 9, 0, tzinfo=KST)
    rows = [
        {
            "market": "KRW-BTC",
            "opened_at": base + timedelta(hours=i),
            "open": base_price,
            "high": base_price * 1.005,
            "low": base_price * 0.995,
            "close": base_price,
            "volume": volume,
            "quote_volume": base_price * volume,
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def _inject_fractal_up(df: pd.DataFrame, idx: int, high_val: float) -> pd.DataFrame:
    df = df.copy()
    df.at[idx, "high"] = high_val
    df.at[idx, "close"] = high_val
    for i in [idx - 2, idx - 1, idx + 1, idx + 2]:
        if 0 <= i < len(df):
            df.at[i, "high"] = high_val * 0.99
    return df


def _buy_fixture() -> pd.DataFrame:
    """KrFractal BUY 테스트와 동일 패턴: idx27 up-fractal 9500, 마지막 close 10000, vol 1.5."""
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    df = _inject_fractal_up(df, 27, high_val=9500.0)
    df.at[len(df) - 1, "volume"] = 1.5
    df.at[len(df) - 1, "close"] = 10000.0
    return df


def test_matches_kr_fractal_on_same_input() -> None:
    """회귀: 동일 입력에서 KrFractal과 방향·모드·강도·레벨·타임프레임 일치."""
    df = _buy_fixture()
    crypto = FractalStrategy().evaluate("KRW-BTC", df)
    kr = KrFractalStrategy().evaluate("KRW-BTC", df)
    assert len(crypto) == len(kr) == 1
    c, k = crypto[0], kr[0]
    assert c.direction == k.direction == SignalDirection.BUY
    assert c.mode == k.mode == StrategyMode.FRACTAL_BREAKOUT
    assert c.strength == k.strength
    assert c.indicators.fractal_up == k.indicators.fractal_up == pytest.approx(9500.0)
    assert c.timeframe == Timeframe.HOUR_1
    assert c.price == pytest.approx(k.price)


def test_volume_below_threshold_no_signal() -> None:
    df = _make_candles(30, volume=1.0)
    df = _inject_fractal_up(df, 27, high_val=9500.0)
    df.at[len(df) - 1, "close"] = 10000.0  # vol ratio ~1.0 < 1.2
    strat = FractalStrategy(fractal_volume_threshold=1.2)
    assert strat.evaluate("KRW-BTC", df) == []


def test_strong_when_volume_exceeds_strong() -> None:
    df = _buy_fixture()
    df.at[len(df) - 1, "volume"] = 2.5  # ratio 2.5 >= 2.0 → STRONG
    sigs = FractalStrategy().evaluate("KRW-BTC", df)
    assert len(sigs) == 1
    assert sigs[0].strength == SignalStrength.STRONG


def test_stale_fractal_filtered_by_max_age() -> None:
    """확정 프랙탈이 max_age보다 오래되면 신호 없음 (KrFractal엔 없는 추가 규율)."""
    df = _make_candles(30, base_price=10000.0, volume=1.0)
    df = _inject_fractal_up(df, 5, high_val=9500.0)  # age = 30-1-5 = 24 > 20
    df.at[len(df) - 1, "volume"] = 1.5
    df.at[len(df) - 1, "close"] = 9600.0  # > 9500 이지만 프랙탈이 stale
    strat = FractalStrategy(fractal_max_age=20)
    assert strat.evaluate("KRW-BTC", df) == []


def test_fresh_fractal_within_max_age_fires() -> None:
    df = _buy_fixture()  # age = 2 <= 20
    sigs = FractalStrategy(fractal_max_age=20).evaluate("KRW-BTC", df)
    assert len(sigs) == 1
    assert sigs[0].direction == SignalDirection.BUY


def test_insufficient_data_returns_empty() -> None:
    assert FractalStrategy().evaluate("KRW-BTC", _make_candles(5)) == []


def test_name() -> None:
    assert FractalStrategy().name == "v3_fractal"
