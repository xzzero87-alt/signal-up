from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import pandas as pd

    from signal_program.models import Signal


class Strategy(Protocol):
    name: str

    def evaluate(self, market: str, candles: "pd.DataFrame") -> "list[Signal]": ...
