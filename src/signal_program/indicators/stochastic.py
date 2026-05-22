"""Stochastic Slow 지표 — ADR-0010 §3 (Sto 15/85 엄격 임계값).

compute_stochastic_slow(candles, k=14, d=3) -> pd.DataFrame
  Fast %K = 100 * (close - lowest_low_k) / (highest_high_k - lowest_low_k)
  Slow %K = SMA(Fast %K, d)
  Slow %D = SMA(Slow %K, d)

ADR-0010 채택: Sto 임계값 oversold=15, overbought=85 (엄격).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_stochastic_slow(
    candles: pd.DataFrame,
    k: int = 14,
    d: int = 3,
) -> pd.DataFrame:
    """Stochastic Slow — 봉 마감가(close) 기준 순수 함수.

    Parameters
    ----------
    candles:
        'close', 'high', 'low' 컬럼이 있는 캔들 DataFrame.
    k:
        Fast %K 계산 기간 (기본 14봉).
    d:
        Slow %K / %D 평활 기간 (기본 3봉).

    Returns
    -------
    pd.DataFrame with columns:
        stoch_k — Slow %K ∈ [0, 100]
        stoch_d — Slow %D ∈ [0, 100]

    Notes
    -----
    - high == low (hl_range=0)인 경우 fast_k = 50.0 (중립값).
    - NaN 행 수: stoch_k = k+d-2, stoch_d = k+2d-3.
    """
    close = candles["close"]
    high = candles["high"]
    low = candles["low"]

    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    hl_range = highest_high - lowest_low

    # hl_range=0일 때 ZeroDivisionError 방지 → 중립값 50.0
    fast_k_arr = np.where(
        hl_range > 0,
        (close - lowest_low) / hl_range * 100.0,
        50.0,
    )
    fast_k = pd.Series(fast_k_arr, index=close.index, dtype=float)
    # lowest_low가 NaN인 구간(첫 k-1 봉)은 fast_k도 NaN으로 복원
    fast_k = fast_k.where(hl_range.notna(), other=np.nan)

    slow_k = fast_k.rolling(d).mean()
    slow_d = slow_k.rolling(d).mean()

    return pd.DataFrame({"stoch_k": slow_k, "stoch_d": slow_d})
