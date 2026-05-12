"""Bollinger Bands 단위 테스트.

레퍼런스 픽스처: 등차수열 [10, 11, ..., 20], period=3, std_mult=2.0
  - index 2: window=[10,11,12], mean=11, std=1 → upper=13, lower=9, pct_b=0.75
  - index 10: window=[18,19,20], mean=19, std=1 → upper=21, lower=17, pct_b=0.75
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from signal_program.indicators.bollinger import bollinger

_COLS = {"bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct_b"}


@pytest.fixture
def arith_series() -> pd.Series[float]:
    return pd.Series(np.arange(10.0, 21.0))


# ---------------------------------------------------------------------------
# 레퍼런스 정확도 (오차 ≤ 0.01%)
# ---------------------------------------------------------------------------


def test_bollinger_columns(arith_series: pd.Series[float]) -> None:
    assert set(bollinger(arith_series, period=3).columns) == _COLS


def test_bollinger_reference_first_window(arith_series: pd.Series[float]) -> None:
    r = bollinger(arith_series, period=3, std_mult=2.0)
    assert r["bb_middle"].iloc[2] == pytest.approx(11.0, rel=1e-4)
    assert r["bb_upper"].iloc[2] == pytest.approx(13.0, rel=1e-4)
    assert r["bb_lower"].iloc[2] == pytest.approx(9.0, rel=1e-4)
    assert r["bb_pct_b"].iloc[2] == pytest.approx(0.75, rel=1e-4)


def test_bollinger_reference_last_window(arith_series: pd.Series[float]) -> None:
    r = bollinger(arith_series, period=3, std_mult=2.0)
    assert r["bb_middle"].iloc[-1] == pytest.approx(19.0, rel=1e-4)
    assert r["bb_upper"].iloc[-1] == pytest.approx(21.0, rel=1e-4)
    assert r["bb_lower"].iloc[-1] == pytest.approx(17.0, rel=1e-4)
    assert r["bb_pct_b"].iloc[-1] == pytest.approx(0.75, rel=1e-4)


def test_bollinger_width_formula(arith_series: pd.Series[float]) -> None:
    r = bollinger(arith_series, period=3, std_mult=2.0)
    valid = r.dropna()
    expected = (valid["bb_upper"] - valid["bb_lower"]) / valid["bb_middle"]
    pd.testing.assert_series_equal(
        valid["bb_width"].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_names=False,
        rtol=1e-6,
    )


def test_bollinger_warmup_nan(arith_series: pd.Series[float]) -> None:
    r = bollinger(arith_series, period=3, std_mult=2.0)
    assert r["bb_middle"].iloc[:2].isna().all()


# ---------------------------------------------------------------------------
# 경계값 parametrize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period,std_mult",
    [
        (2, 2.0),
        (200, 2.0),
        (20, 0.5),
        (20, 3.0),
    ],
)
def test_bollinger_boundary_values(period: int, std_mult: float) -> None:
    n = max(period + 10, 220)
    close = pd.Series(np.arange(1.0, n + 1.0))
    r = bollinger(close, period=period, std_mult=std_mult)
    assert set(r.columns) == _COLS
    valid = r.iloc[period:]
    assert valid["bb_middle"].notna().all()
    assert (valid["bb_upper"] >= valid["bb_middle"]).all()
    assert (valid["bb_middle"] >= valid["bb_lower"]).all()


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
def test_bollinger_no_exception_positive_series(values: list[float]) -> None:
    close = pd.Series(values)
    r = bollinger(close, period=20, std_mult=2.0)
    assert isinstance(r, pd.DataFrame)
    assert set(r.columns) == _COLS
