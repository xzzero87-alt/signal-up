from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from signal_program.models import Signal


class BbCciStrategy:
    name = "bb_cci"

    def __init__(
        self,
        bb_period: int = 20,
        bb_std_mult: float = 2.0,
        cci_period: int = 20,
        cci_threshold_normal: int = 100,
        cci_threshold_strong: int = 200,
        volume_ratio_min_a: float = 1.0,
        volume_lookback: int = 20,
    ) -> None:
        self.bb_period = bb_period
        self.bb_std_mult = bb_std_mult
        self.cci_period = cci_period
        self.cci_threshold_normal = cci_threshold_normal
        self.cci_threshold_strong = cci_threshold_strong
        self.volume_ratio_min_a = volume_ratio_min_a
        self.volume_lookback = volume_lookback

    def evaluate(self, market: str, candles: "pd.DataFrame") -> "list[Signal]":
        raise NotImplementedError
