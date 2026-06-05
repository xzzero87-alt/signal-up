"""Wilder RSI 지표 — 설계 v2.3 §3.3 (RSI(2) 평균회귀 V5).

rsi(close, period) -> Series
  Wilder 평활: avg_gain/avg_loss = ewm(alpha=1/period, adjust=False).
  SMA 방식 금지 (값이 달라짐).

선행 NaN(diff 첫 봉)은 ewm seed에서 자동 스킵 → 첫 실제 delta가 seed가 된다.
완전 평탄 구간(이득·손실 모두 0)은 중립값 50.0으로 처리한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder 평활 RSI ∈ [0, 100].

    Parameters
    ----------
    close:
        종가 Series (봉 마감가 기준).
    period:
        RSI 기간 (기본 14, RSI(2) 전략은 2).

    Returns
    -------
    pd.Series — close와 동일 인덱스. 첫 봉은 NaN (delta 없음).

    Notes
    -----
    - avg_loss == 0 (연속 상승) → RSI = 100.
    - avg_gain == avg_loss == 0 (완전 평탄) → RSI = 50 (중립).
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        out = 100.0 - 100.0 / (1.0 + rs)

    # avg_loss == 0 → 상승만 존재 → 100 ; 단, 완전 평탄(둘 다 0)은 50
    out = out.mask(avg_loss == 0.0, 100.0)
    out = out.mask((avg_gain == 0.0) & (avg_loss == 0.0), 50.0)
    # 선행 NaN(warmup) 복원
    return out.where(avg_gain.notna(), other=np.nan)
