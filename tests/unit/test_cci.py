"""CCI 단위 테스트.

레퍼런스 픽스처: H=L=C=[1, 2, ..., 20], period=5
  TP = close (H=L=C이므로)
  index 4:  TP=[1,2,3,4,5],  mean=3.0,  MAD=1.2 → CCI = 2/0.018 ≈ 111.111
  index 19: TP=[16,17,18,19,20], mean=18.0, MAD=1.2 → CCI = 2/0.018 ≈ 111.111
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from signal_program.indicators.cci import cci

_EXPECTED_CCI = 2.0 / 0.018  # ≈ 111.111...


@pytest.fixture
def arith_ohlc() -> tuple[pd.Series[float], pd.Series[float], pd.Series[float]]:
    vals: pd.Series[float] = pd.Series(np.arange(1.0, 21.0))
    return vals, vals, vals


# ---------------------------------------------------------------------------
# 레퍼런스 정확도 (오차 ≤ 0.01%)
# ---------------------------------------------------------------------------


def test_cci_reference_first_window(
    arith_ohlc: tuple[pd.Series[float], pd.Series[float], pd.Series[float]],
) -> None:
    high, low, close = arith_ohlc
    result = cci(high, low, close, period=5)
    assert result.iloc[4] == pytest.approx(_EXPECTED_CCI, rel=1e-4)


def test_cci_reference_last_window(
    arith_ohlc: tuple[pd.Series[float], pd.Series[float], pd.Series[float]],
) -> None:
    high, low, close = arith_ohlc
    result = cci(high, low, close, period=5)
    assert result.iloc[-1] == pytest.approx(_EXPECTED_CCI, rel=1e-4)


def test_cci_warmup_nan(
    arith_ohlc: tuple[pd.Series[float], pd.Series[float], pd.Series[float]],
) -> None:
    high, low, close = arith_ohlc
    result = cci(high, low, close, period=5)
    assert result.iloc[:4].isna().all()


def test_cci_returns_series(
    arith_ohlc: tuple[pd.Series[float], pd.Series[float], pd.Series[float]],
) -> None:
    high, low, close = arith_ohlc
    result = cci(high, low, close, period=5)
    assert isinstance(result, pd.Series)
    assert len(result) == len(close)


# ---------------------------------------------------------------------------
# 경계값 parametrize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("period", [2, 5, 20, 200])
def test_cci_boundary_periods(period: int) -> None:
    n = max(period + 10, 220)
    vals = pd.Series(np.arange(1.0, n + 1.0))
    result = cci(vals, vals, vals, period=period)
    assert isinstance(result, pd.Series)
    assert len(result) == n
    assert result.iloc[period:].notna().all()


# ---------------------------------------------------------------------------
# Hypothesis property: 양수 시계열에 예외 없음
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=25,
        max_size=300,
    )
)
@settings(max_examples=100)
def test_cci_no_exception_positive_series(values: list[float]) -> None:
    series: pd.Series[float] = pd.Series(values)
    result = cci(series, series, series, period=20)
    assert isinstance(result, pd.Series)
    assert len(result) == len(series)
