"""OBV (On Balance Volume) 지표 — ADR-0010 §1 V2 거래량 지표.

compute_obv(candles, lookback=20) -> pd.DataFrame
  Columns:
    obv       : 누적 OBV raw 값
    buy_score : [0, 1] — OBV가 MA 대비 상승 시 높음
    sell_score: [0, 1] — OBV가 MA 대비 하락 시 높음

ADR-0010 AI 리스크 #1 수정:
  naive: (obv - obv_ma) / obv_ma — obv_ma < 0이면 부호 반전
  fix:   (obv - obv_ma) / abs(obv_ma) — 항상 올바른 방향
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_obv(candles: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """OBV 누적 + lookback 이동평균 기반 정규화 스코어.

    Parameters
    ----------
    candles:
        'close', 'volume' 컬럼이 있는 캔들 DataFrame.
    lookback:
        OBV 이동평균 기간 (기본 20봉).

    Returns
    -------
    pd.DataFrame with columns:
        obv        — raw 누적 OBV
        buy_score  — clip((obv - obv_ma) / abs(obv_ma), 0, 1)
        sell_score — clip((obv_ma - obv) / abs(obv_ma), 0, 1)

    Notes
    -----
    - 첫 봉은 이전 가격이 없어 direction=0 → obv=0.
    - buy_score / sell_score는 첫 (lookback-1)개 행이 NaN.
    - abs() 분모로 obv_ma 음수 시 부호 반전 방지 (ADR-0010 리스크 #1).
    """
    close = candles["close"]
    volume = candles["volume"]

    # +1 상승 / -1 하락 / 0 동일 (첫 봉 diff=NaN → 0으로 채움)
    direction = np.sign(close.diff().fillna(0.0))
    obv: pd.Series[float] = (direction * volume).cumsum()

    obv_ma = obv.rolling(lookback).mean()

    # abs() 분모: obv_ma=0이면 NaN 유지 → score는 NaN (fillna 하지 않음)
    safe_denom: pd.Series[float] = obv_ma.abs().replace(0.0, np.nan)

    buy_score = ((obv - obv_ma) / safe_denom).clip(0.0, 1.0)
    sell_score = ((obv_ma - obv) / safe_denom).clip(0.0, 1.0)

    return pd.DataFrame({"obv": obv, "buy_score": buy_score, "sell_score": sell_score})
