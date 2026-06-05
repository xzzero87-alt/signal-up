"""Donchian 채널 지표 — TDD RED→GREEN (설계 v2.3 §3.2 / §7).

핵심 검증:
- dc_upper[t] = max(high[t-period .. t-1])  → **현재 봉 제외** (look-ahead 방지)
- dc_lower[t] = min(low[t-period .. t-1])
- dc_middle = (dc_upper + dc_lower) / 2
- 데이터 < period 구간은 NaN
"""

from __future__ import annotations

import math

import pandas as pd

from signal_program.indicators.donchian import donchian

# 고정 배열 (period=3 수계산):
#   idx :   0   1   2   3   4   5
#   high:  10  12  11  15   9  14
#   low :   8   9  10   9   7  11
_HIGH = [10.0, 12.0, 11.0, 15.0, 9.0, 14.0]
_LOW = [8.0, 9.0, 10.0, 9.0, 7.0, 11.0]


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"high": _HIGH, "low": _LOW})


def test_dc_upper_excludes_current_bar() -> None:
    """dc_upper[3]는 high[0..2]의 max(=12)이어야 하며 현재 봉 high[3]=15는 제외."""
    df = _frame()
    out = donchian(df["high"], df["low"], period=3)
    assert out["dc_upper"].iloc[3] == 12.0  # max(10,12,11), 15 제외
    assert out["dc_upper"].iloc[4] == 15.0  # max(12,11,15)
    assert out["dc_upper"].iloc[5] == 15.0  # max(11,15,9)


def test_dc_lower_excludes_current_bar() -> None:
    df = _frame()
    out = donchian(df["high"], df["low"], period=3)
    assert out["dc_lower"].iloc[3] == 8.0  # min(8,9,10)
    assert out["dc_lower"].iloc[4] == 9.0  # min(9,10,9)
    assert out["dc_lower"].iloc[5] == 7.0  # min(10,9,7)


def test_dc_middle_is_mean_of_band() -> None:
    df = _frame()
    out = donchian(df["high"], df["low"], period=3)
    assert out["dc_middle"].iloc[3] == 10.0  # (12+8)/2
    assert out["dc_middle"].iloc[4] == 12.0  # (15+9)/2
    assert out["dc_middle"].iloc[5] == 11.0  # (15+7)/2


def test_warmup_region_is_nan() -> None:
    """현재 봉 제외 + period 누적 → idx 0..period-1 은 NaN."""
    df = _frame()
    out = donchian(df["high"], df["low"], period=3)
    for i in range(3):
        assert math.isnan(out["dc_upper"].iloc[i])
        assert math.isnan(out["dc_lower"].iloc[i])
        assert math.isnan(out["dc_middle"].iloc[i])


def test_columns_and_length() -> None:
    df = _frame()
    out = donchian(df["high"], df["low"], period=3)
    assert list(out.columns) == ["dc_upper", "dc_lower", "dc_middle"]
    assert len(out) == len(df)


def test_default_period_20_all_nan_when_short() -> None:
    """기본 period=20, 데이터 10봉 → 전부 NaN (신호 미발생 보장의 기반)."""
    high = pd.Series([float(i) for i in range(10)])
    low = pd.Series([float(i) - 1 for i in range(10)])
    out = donchian(high, low)
    assert out["dc_upper"].isna().all()
