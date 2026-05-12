from enum import StrEnum


class Timeframe(StrEnum):
    HOUR_1 = "60"


class StrategyMode(StrEnum):
    MEAN_REVERSION = "A"
    SQUEEZE_BREAKOUT = "B"


class SignalDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"


class SignalStrength(StrEnum):
    NORMAL = "normal"
    STRONG = "strong"
