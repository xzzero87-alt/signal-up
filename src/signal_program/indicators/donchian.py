"""Donchian 채널 지표 — 설계 v2.3 §3.2 (터틀식 추세추종 V4).

donchian(high, low, period) -> DataFrame(dc_upper, dc_lower, dc_middle)
  dc_upper[t] = max(high[t-period .. t-1])  — **현재 봉 제외** (봉 마감 기준, 자기충족 방지)
  dc_lower[t] = min(low[t-period .. t-1])
  dc_middle   = (dc_upper + dc_lower) / 2

pandas/numpy만 사용. 데이터 < period 구간은 NaN.
"""

from __future__ import annotations

import pandas as pd


def donchian(high: pd.Series, low: pd.Series, period: int = 20) -> pd.DataFrame:
    """Donchian 채널 — 현재 봉을 제외한 직전 ``period`` 봉 기준.

    Parameters
    ----------
    high:
        고가 Series.
    low:
        저가 Series.
    period:
        채널 룩백 기간 (기본 20봉).

    Returns
    -------
    pd.DataFrame with columns:
        dc_upper  — 직전 period 봉 최고가 (현재 봉 제외)
        dc_lower  — 직전 period 봉 최저가 (현재 봉 제외)
        dc_middle — (dc_upper + dc_lower) / 2

    Notes
    -----
    ``shift(1)``로 현재 봉을 제외한다. 이를 빠뜨리면 look-ahead가 되어
    돌파 신호가 자기충족된다 (close > dc_upper에 현재 high가 끼면 무의미).
    """
    dc_upper = high.shift(1).rolling(period).max()
    dc_lower = low.shift(1).rolling(period).min()
    dc_middle = (dc_upper + dc_lower) / 2.0

    return pd.DataFrame({"dc_upper": dc_upper, "dc_lower": dc_lower, "dc_middle": dc_middle})
