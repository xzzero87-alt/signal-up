"""Williams Fractal 확정 로직 — 마켓 중립 공용 모듈 (설계 v2.3 §3.1).

KrFractalStrategy(ADR-0018)에서 추출. 국장/암호화폐 공용.
확정 기준: n번째 봉의 프랙탈은 n+2 봉 마감 후 확정 (5봉 패턴, 미래 참조 금지).

국장 전용 가정(타임프레임 추론 등)은 포함하지 않는다 — 순수 프랙탈 계산만.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def find_fractals(df: pd.DataFrame, lookback: int) -> tuple[float | None, int, float | None, int]:
    """최근 확정 Williams Fractal (up/down) 레벨과 봉 거리(age)를 반환한다.

    확정 기준: n번째 봉의 프랙탈은 n+2 봉 마감 후 확정 → 최근 확정 인덱스 = iloc[-3].
    """
    n = len(df)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    up_level: float | None = None
    up_age: int = 0
    down_level: float | None = None
    down_age: int = 0

    start = n - 3  # 최근 확정 위치
    stop = max(2, start - lookback)

    for i in range(start, stop - 1, -1):
        if up_level is None and (
            high[i] > high[i - 1]
            and high[i] > high[i - 2]
            and high[i] > high[i + 1]
            and high[i] > high[i + 2]
        ):
            up_level = float(high[i])
            up_age = n - 1 - i
        if down_level is None and (
            low[i] < low[i - 1]
            and low[i] < low[i - 2]
            and low[i] < low[i + 1]
            and low[i] < low[i + 2]
        ):
            down_level = float(low[i])
            down_age = n - 1 - i
        if up_level is not None and down_level is not None:
            break

    return up_level, up_age, down_level, down_age
