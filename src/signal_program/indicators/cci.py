from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    import pandas as pd


def _mean_abs_dev(arr: npt.NDArray[np.float64]) -> float:
    return float(np.abs(arr - arr.mean()).mean())


def cci(
    high: pd.Series[float],
    low: pd.Series[float],
    close: pd.Series[float],
    period: int = 20,
) -> pd.Series[float]:
    """Commodity Channel Index — Typical Price 기반 표준 공식.

    CCI = (TP - MA) / (0.015 * MAD)
    where TP = (high + low + close) / 3, MAD = mean absolute deviation.
    First (period-1) rows are NaN.
    """
    tp: pd.Series[float] = (high + low + close) / 3.0
    ma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(_mean_abs_dev, raw=True)
    return (tp - ma) / (0.015 * mad)
