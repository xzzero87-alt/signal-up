"""Rsi2Strategy — Connors RSI(2) + 추세필터 (설계 v2.3 §3.3 / §7). TDD RED→GREEN.

매수: close > sma200 AND rsi2 < 10   매도: close < sma200 AND rsi2 > 90
STRONG: rsi2 < 5 (매수) / rsi2 > 95 (매도)
핵심: 추세필터 아래에서의 과매도는 신호가 아니다 (하락장 계좌 보호).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode
from signal_program.strategies.rsi2 import Rsi2Strategy

KST = timezone(timedelta(hours=9))


def _candles(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    base = datetime(2026, 1, 1, 9, 0, tzinfo=KST)
    rows = [
        {
            "market": "KRW-BTC",
            "opened_at": base + timedelta(hours=i),
            "open": closes[i],
            "high": closes[i],
            "low": closes[i],
            "close": closes[i],
            "volume": 1.0,
            "quote_volume": closes[i],
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


# 손계산 검증된 픽스처 (period=2, alpha=0.5):
#   상승추세 +0.5/봉 → avg_gain≈0.5, avg_loss≈0.
#   마지막 봉 -5 한 번 → rsi2≈9.09 (NORMAL),  연속 -5 두 번 → rsi2≈3.23 (STRONG).
def _uptrend_dip(strong: bool) -> list[float]:
    closes = [100.0 + 0.5 * i for i in range(210)]
    if strong:
        closes[-2] = closes[-3] - 5.0
        closes[-1] = closes[-2] - 5.0
    else:
        closes[-1] = closes[-2] - 5.0
    return closes


#   하락추세 -0.5/봉 → close < sma200, rsi2 낮음.
#   마지막 봉 +5 한 번 → rsi2≈90.9 (NORMAL), 연속 +5 두 번 → rsi2≈96.8 (STRONG).
def _downtrend_pop(strong: bool) -> list[float]:
    closes = [200.0 - 0.5 * i for i in range(210)]
    if strong:
        closes[-2] = closes[-3] + 5.0
        closes[-1] = closes[-2] + 5.0
    else:
        closes[-1] = closes[-2] + 5.0
    return closes


STRAT = Rsi2Strategy()


def test_buy_when_above_trend_and_oversold() -> None:
    sigs = STRAT.evaluate("KRW-BTC", _candles(_uptrend_dip(strong=False)))
    buys = [s for s in sigs if s.direction == SignalDirection.BUY]
    assert len(buys) == 1
    assert buys[0].mode == StrategyMode.RSI2_REVERSION
    assert buys[0].strength == SignalStrength.NORMAL
    assert buys[0].indicators.rsi2 is not None
    assert buys[0].indicators.trend_sma is not None


def test_buy_strong_when_deeply_oversold() -> None:
    sigs = STRAT.evaluate("KRW-BTC", _candles(_uptrend_dip(strong=True)))
    buys = [s for s in sigs if s.direction == SignalDirection.BUY]
    assert len(buys) == 1
    assert buys[0].strength == SignalStrength.STRONG  # rsi2 < 5


def test_oversold_below_trend_is_no_signal() -> None:
    """핵심 케이스: 추세필터 아래(close<sma200)에서 과매도여도 무신호."""
    closes = [200.0 - 0.5 * i for i in range(210)]  # 순수 하락 → rsi2=0(과매도), close<sma
    sigs = STRAT.evaluate("KRW-BTC", _candles(closes))
    assert sigs == []


def test_sell_when_below_trend_and_overbought() -> None:
    sigs = STRAT.evaluate("KRW-BTC", _candles(_downtrend_pop(strong=False)))
    sells = [s for s in sigs if s.direction == SignalDirection.SELL]
    assert len(sells) == 1
    assert sells[0].mode == StrategyMode.RSI2_REVERSION
    assert sells[0].strength == SignalStrength.NORMAL


def test_sell_strong_when_deeply_overbought() -> None:
    sigs = STRAT.evaluate("KRW-BTC", _candles(_downtrend_pop(strong=True)))
    sells = [s for s in sigs if s.direction == SignalDirection.SELL]
    assert len(sells) == 1
    assert sells[0].strength == SignalStrength.STRONG  # rsi2 > 95


def test_insufficient_data_returns_empty_no_exception() -> None:
    """캔들 < trend_period+1 → 예외 없이 빈 리스트."""
    closes = [100.0 + i for i in range(150)]  # < 201
    assert STRAT.evaluate("KRW-BTC", _candles(closes)) == []


def test_name() -> None:
    assert Rsi2Strategy().name == "v5_rsi2"
