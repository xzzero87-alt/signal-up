"""DonchianStrategy — 터틀식 추세추종 (설계 v2.3 §3.2 / §7). TDD RED→GREEN.

매수: close > dc_upper(entry=20)   매도: close < dc_lower(exit=10)
STRONG: volume_ratio >= donchian_volume_strong(1.5).  거래량은 진입 게이트가 아님(강도만).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode
from signal_program.strategies.donchian import DonchianStrategy

KST = timezone(timedelta(hours=9))


def _candles(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    if volumes is None:
        volumes = [1.0] * n
    base = datetime(2026, 1, 1, 9, 0, tzinfo=KST)
    rows = [
        {
            "market": "KRW-BTC",
            "opened_at": base + timedelta(hours=i),
            "open": closes[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "volume": volumes[i],
            "quote_volume": closes[i] * volumes[i],
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def _base(n: int = 30) -> tuple[list[float], list[float], list[float]]:
    """직전 채널이 평탄: high=100, low=90, close=95. 마지막 봉만 교체해 사용."""
    return [100.0] * n, [90.0] * n, [95.0] * n


STRAT = DonchianStrategy()


def test_buy_on_upper_breakout() -> None:
    highs, lows, closes = _base()
    closes[-1] = 105.0  # > dc_upper(=100, 직전 20봉 최고가)
    highs[-1] = 106.0
    sigs = STRAT.evaluate("KRW-BTC", _candles(highs, lows, closes))
    buys = [s for s in sigs if s.direction == SignalDirection.BUY]
    assert len(buys) == 1
    assert buys[0].mode == StrategyMode.DONCHIAN_BREAKOUT
    assert buys[0].indicators.dc_upper == 100.0


def test_sell_on_exit_channel_break() -> None:
    highs, lows, closes = _base()
    closes[-1] = 85.0  # < dc_lower(exit=10, 직전 10봉 최저가=90)
    lows[-1] = 84.0
    sigs = STRAT.evaluate("KRW-BTC", _candles(highs, lows, closes))
    sells = [s for s in sigs if s.direction == SignalDirection.SELL]
    assert len(sells) == 1
    assert sells[0].mode == StrategyMode.DONCHIAN_BREAKOUT
    assert sells[0].indicators.dc_lower == 90.0


def test_no_signal_inside_channel() -> None:
    highs, lows, closes = _base()
    closes[-1] = 95.0  # 90 < 95 < 100 → 돌파 없음
    sigs = STRAT.evaluate("KRW-BTC", _candles(highs, lows, closes))
    assert sigs == []


def test_strong_when_volume_high() -> None:
    highs, lows, closes = _base()
    closes[-1] = 105.0
    vols = [1.0] * 30
    vols[-1] = 2.0  # ratio 2.0 >= 1.5 → STRONG
    sigs = STRAT.evaluate("KRW-BTC", _candles(highs, lows, closes, vols))
    buys = [s for s in sigs if s.direction == SignalDirection.BUY]
    assert len(buys) == 1
    assert buys[0].strength == SignalStrength.STRONG


def test_breakout_still_fires_on_low_volume() -> None:
    """거래량 필터는 진입 게이트가 아니다 — 저거래량 돌파도 NORMAL 신호."""
    highs, lows, closes = _base()
    closes[-1] = 105.0
    vols = [1.0] * 30
    vols[-1] = 0.5  # ratio 0.5 < 1.5 → 그래도 신호 발생, NORMAL
    sigs = STRAT.evaluate("KRW-BTC", _candles(highs, lows, closes, vols))
    buys = [s for s in sigs if s.direction == SignalDirection.BUY]
    assert len(buys) == 1
    assert buys[0].strength == SignalStrength.NORMAL


def test_current_bar_excluded_from_channel() -> None:
    """현재 봉 high(=200)는 채널에서 제외 → dc_upper=100, close 105 > 100 → BUY.

    만약 현재 봉을 포함했다면 dc_upper=200, close 105 < 200 → 신호 없음(잘못).
    """
    highs, lows, closes = _base()
    highs[-1] = 200.0  # 현재 봉의 비정상적 고가
    closes[-1] = 105.0
    sigs = STRAT.evaluate("KRW-BTC", _candles(highs, lows, closes))
    buys = [s for s in sigs if s.direction == SignalDirection.BUY]
    assert len(buys) == 1  # 제외했으므로 돌파 성립


def test_insufficient_data_returns_empty() -> None:
    highs, lows, closes = _base(n=10)
    assert STRAT.evaluate("KRW-BTC", _candles(highs, lows, closes)) == []


def test_name() -> None:
    assert DonchianStrategy().name == "v4_donchian"
