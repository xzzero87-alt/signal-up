from enum import StrEnum


class Timeframe(StrEnum):
    HOUR_1 = "60"


class StrategyMode(StrEnum):
    MEAN_REVERSION = "A"
    SQUEEZE_BREAKOUT = "B"
    WEIGHTED_SCORE = "C"  # V2 FourIndicatorStrategy (ADR-0010)


class SignalDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"


class SignalStrength(StrEnum):
    NORMAL = "normal"
    STRONG = "strong"
