from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from signal_program.enums import (
    SignalDirection,
    SignalStrength,
    StrategyMode,
    Timeframe,
)


class Candle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float


class IndicatorSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width: float
    bb_pct_b: float
    cci: float
    volume_ratio: float = Field(ge=0.0)
    bb_width_quantile: float | None = None


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str
    timeframe: Timeframe
    mode: StrategyMode
    direction: SignalDirection
    strength: SignalStrength
    price: float
    triggered_at: datetime
    indicators: IndicatorSnapshot
