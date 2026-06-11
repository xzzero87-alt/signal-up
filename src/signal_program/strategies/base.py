from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd

    from signal_program.models import Signal


@runtime_checkable
class SupportsExit(Protocol):
    """선택적 보조 프로토콜 — 청산 판단을 전략에 위임 (ADR-0021).

    구현 시 엔진은 BB 타깃 청산을 적용하지 않고, max_holding_bars 캡은 항상 유지.
    """

    def should_exit(self, market: str, candles: pd.DataFrame, entry_bar_idx: int) -> bool: ...


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
