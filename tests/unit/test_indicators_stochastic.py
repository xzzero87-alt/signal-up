"""compute_stochastic_slow — TDD RED → GREEN.

Stochastic Slow:
  Fast %K = 100 * (close - lowest_low_k) / (highest_high_k - lowest_low_k)
  Slow %K = SMA(Fast %K, d)
  Slow %D = SMA(Slow %K, d)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from signal_program.indicators.stochastic import compute_stochastic_slow

KST = timezone(timedelta(hours=9))


def make_candles(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    if highs is None:
        highs = closes[:]
    if lows is None:
        lows = closes[:]
    base = datetime(2026, 1, 1, tzinfo=KST)
    rows = [
        {
            "market": "KRW-BTC",
            "opened_at": base + timedelta(hours=i),
            "open": c,
            "high": h,
            "low": l,
            "close": c,
            "volume": 1.0,
            "quote_volume": c,
        }
        for i, (c, h, l) in enumerate(zip(closes, highs, lows))
    ]
    return pd.DataFrame(rows)


def make_uniform_candles(
    n: int,
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
) -> pd.DataFrame:
    if high is None:
        high = close
    if low is None:
        low = close
    return make_candles(
        closes=[close] * n,
        highs=[high] * n,
        lows=[low] * n,
    )


# ─── 경계값 테스트 ─────────────────────────────────────────────────────────────


class TestStochasticBoundary:
    """close가 항상 high이면 slow_k = 100, 항상 low이면 slow_k = 0."""

    def test_all_close_at_high_gives_100(self) -> None:
        """close = high (항상 최고점) → slow %K = 100.0."""
        candles = make_uniform_candles(n=25, close=100.0, high=100.0, low=80.0)
        result = compute_stochastic_slow(candles, k=14, d=3)
        valid_k = result["stoch_k"].dropna()
        assert len(valid_k) > 0, "유효한 stoch_k 값이 없음"
        assert np.allclose(valid_k.to_numpy(), 100.0), (
            f"close=high 조건에서 stoch_k≠100: {valid_k.tolist()}"
        )

    def test_all_close_at_low_gives_0(self) -> None:
        """close = low (항상 최저점) → slow %K = 0.0."""
        candles = make_uniform_candles(n=25, close=80.0, high=100.0, low=80.0)
        result = compute_stochastic_slow(candles, k=14, d=3)
        valid_k = result["stoch_k"].dropna()
        assert len(valid_k) > 0
        assert np.allclose(valid_k.to_numpy(), 0.0), (
            f"close=low 조건에서 stoch_k≠0: {valid_k.tolist()}"
        )

    def test_close_at_midpoint_gives_50(self) -> None:
        """close = (high+low)/2 → fast %K = 50 → slow %K = 50."""
        # high=120, low=80, close=100 → fast_k = (100-80)/(120-80)*100 = 50
        candles = make_uniform_candles(n=25, close=100.0, high=120.0, low=80.0)
        result = compute_stochastic_slow(candles, k=14, d=3)
        valid_k = result["stoch_k"].dropna()
        assert np.allclose(valid_k.to_numpy(), 50.0)

    def test_stoch_d_equals_stoch_k_on_constant_fast_k(self) -> None:
        """fast_k가 일정하면 slow_k = slow_d = fast_k."""
        candles = make_uniform_candles(n=30, close=100.0, high=120.0, low=80.0)
        result = compute_stochastic_slow(candles, k=14, d=3)
        valid = result.dropna()
        assert np.allclose(valid["stoch_k"].to_numpy(), valid["stoch_d"].to_numpy())


# ─── NaN 행 수 검증 ───────────────────────────────────────────────────────────


class TestStochasticNaNRows:
    """NaN row 수: stoch_k=(k+d-2), stoch_d=(k+2d-3)."""

    def test_nan_count_default_params(self) -> None:
        """k=14, d=3: stoch_k NaN=15, stoch_d NaN=17."""
        k, d = 14, 3
        n = k + 2 * d - 3 + 5  # stoch_d 유효값 5개
        candles = make_uniform_candles(n=n, close=100.0, high=120.0, low=80.0)
        result = compute_stochastic_slow(candles, k=k, d=d)

        expected_k_nan = k + d - 2    # 15
        expected_d_nan = k + 2 * d - 3  # 17
        assert result["stoch_k"].isna().sum() == expected_k_nan, (
            f"stoch_k NaN={result['stoch_k'].isna().sum()} (기대: {expected_k_nan})"
        )
        assert result["stoch_d"].isna().sum() == expected_d_nan, (
            f"stoch_d NaN={result['stoch_d'].isna().sum()} (기대: {expected_d_nan})"
        )

    def test_nan_count_small_params(self) -> None:
        """k=3, d=2: stoch_k NaN=3, stoch_d NaN=4."""
        k, d = 3, 2
        n = k + 2 * d - 3 + 3
        candles = make_uniform_candles(n=n, close=100.0, high=120.0, low=80.0)
        result = compute_stochastic_slow(candles, k=k, d=d)
        assert result["stoch_k"].isna().sum() == k + d - 2
        assert result["stoch_d"].isna().sum() == k + 2 * d - 3


# ─── 범위 검증 ────────────────────────────────────────────────────────────────


class TestStochasticRange:
    def test_range_oscillating_prices(self) -> None:
        """진동 가격에서도 stoch_k, stoch_d ∈ [0, 100]."""
        n = 60
        base, amp = 100.0, 30.0
        closes = [base + amp * math.sin(i * 0.3) for i in range(n)]
        highs = [c + 5.0 for c in closes]
        lows = [c - 5.0 for c in closes]
        result = compute_stochastic_slow(make_candles(closes, highs, lows), k=14, d=3)
        valid = result.dropna()
        assert (valid["stoch_k"] >= 0.0).all()
        assert (valid["stoch_k"] <= 100.0).all()
        assert (valid["stoch_d"] >= 0.0).all()
        assert (valid["stoch_d"] <= 100.0).all()


# ─── 평탄 가격 엣지 케이스 ────────────────────────────────────────────────────


class TestStochasticFlatPrice:
    """high == low (hl_range=0) → ZeroDivisionError 없이 처리."""

    def test_flat_price_no_exception(self) -> None:
        candles = make_uniform_candles(n=25, close=100.0, high=100.0, low=100.0)
        result = compute_stochastic_slow(candles, k=14, d=3)
        assert result is not None

    def test_flat_price_value_in_range(self) -> None:
        candles = make_uniform_candles(n=25, close=100.0, high=100.0, low=100.0)
        result = compute_stochastic_slow(candles, k=14, d=3)
        valid = result.dropna()
        if len(valid) > 0:
            assert (valid["stoch_k"] >= 0.0).all()
            assert (valid["stoch_k"] <= 100.0).all()


# ─── 반환 타입 검증 ──────────────────────────────────────────────────────────


class TestStochasticReturnType:
    def test_returns_dataframe(self) -> None:
        candles = make_uniform_candles(n=25, close=100.0, high=120.0, low=80.0)
        result = compute_stochastic_slow(candles)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self) -> None:
        candles = make_uniform_candles(n=25, close=100.0, high=120.0, low=80.0)
        result = compute_stochastic_slow(candles)
        assert "stoch_k" in result.columns
        assert "stoch_d" in result.columns

    def test_same_length_as_input(self) -> None:
        n = 30
        candles = make_uniform_candles(n=n, close=100.0, high=120.0, low=80.0)
        result = compute_stochastic_slow(candles)
        assert len(result) == n
