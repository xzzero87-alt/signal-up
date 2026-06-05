from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import pandas as pd

    from signal_program.models import Signal


class Strategy(Protocol):
    name: str

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]: ...


def calc_change_pct(candles: pd.DataFrame) -> float | None:
    """전봉 대비 최종 종가 등락률 (%)."""
    if len(candles) < 2:
        return None
    prev = float(candles.iloc[-2]["close"])
    curr = float(candles.iloc[-1]["close"])
    if prev == 0:
        return None
    return round((curr - prev) / prev * 100, 2)
