from enum import StrEnum


class Timeframe(StrEnum):
    HOUR_1 = "60"
    HOUR_2 = "120"  # 120분봉 — KIS 60분봉 2개 집계 (ADR-0016)


class KrMarket(StrEnum):
    """국내 주식 시장 구분 (표시·필터용)."""

    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


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
