from __future__ import annotations

import pandas as pd


def bollinger(
    close: pd.Series[float],
    period: int = 20,
    std_mult: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands (sample std, ddof=1) — 봉 마감가 기준 순수 함수.

    Returns columns: bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b.
    First (period-1) rows are NaN.
    """
    middle = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=1)
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    width = (upper - lower) / middle
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame(
        {
            "bb_upper": upper,
            "bb_middle": middle,
            "bb_lower": lower,
            "bb_width": width,
            "bb_pct_b": pct_b,
        }
    )
