"""BbCciStrategy 모드 A — TDD RED → GREEN 시나리오 13종."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode
from signal_program.strategies.bb_cci import BbCciStrategy

KST = timezone(timedelta(hours=9))


def make_candles(
    closes: list[float],
    volumes: list[float] | None = None,
    market: str = "KRW-BTC",
    start: str = "2026-01-01T00:00+09:00",
) -> pd.DataFrame:
    """합성 캔들 DataFrame. high=close*1.005, low=close*0.995."""
    if volumes is None:
        volumes = [1.0] * len(closes)
    base = datetime.fromisoformat(start)
    rows = [
        {
            "market": market,
            "opened_at": base + timedelta(hours=i),
            "open": c,
            "high": c * 1.005,
            "low": c * 0.995,
            "close": c,
            "volume": v,
            "quote_volume": c * v,
        }
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]
    return pd.DataFrame(rows)


def _buy_candles(vol_ratio: float = 1.2, drop_pct: float = 0.92) -> pd.DataFrame:
    """flat 후 급락 — BB 하단 이탈, CCI 음수 유도."""
    n = 60
    flat = 10_000.0
    closes = [flat] * (n - 1) + [flat * drop_pct]
    volumes = [1.0] * n
    volumes[-1] = vol_ratio * (sum(volumes[-21:-1]) / 20)
    return make_candles(closes, volumes)


def _sell_candles(vol_ratio: float = 1.2, rise_pct: float = 1.08) -> pd.DataFrame:
    """flat 후 급등 — BB 상단 이탈, CCI 양수 유도."""
    n = 60
    flat = 10_000.0
    closes = [flat] * (n - 1) + [flat * rise_pct]
    volumes = [1.0] * n
    volumes[-1] = vol_ratio * (sum(volumes[-21:-1]) / 20)
    return make_candles(closes, volumes)


STRAT = BbCciStrategy()


def _eval(candles: pd.DataFrame) -> list:
    return STRAT.evaluate("KRW-BTC", candles)


# (a) BUY Normal
def test_buy_normal() -> None:
    result = _eval(_buy_candles(vol_ratio=1.2, drop_pct=0.92))
    assert len(result) == 1
    s = result[0]
    assert s.direction == SignalDirection.BUY
    assert s.strength == SignalStrength.NORMAL
    assert s.mode == StrategyMode.MEAN_REVERSION
    assert s.market == "KRW-BTC"
    assert s.triggered_at.tzinfo is not None


# (b) BUY Strong
def test_buy_strong() -> None:
    result = _eval(_buy_candles(drop_pct=0.88))
    assert len(result) == 1
    assert result[0].direction == SignalDirection.BUY
    assert result[0].strength == SignalStrength.STRONG


# (c) BUY 부정 — cci 임계값 미달
def test_buy_negative_cci_too_small() -> None:
    candles = _buy_candles(drop_pct=0.999)
    buy_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 0


# (d) BUY 부정 — 가격이 bb_lower 위
def test_buy_negative_price_above_lower() -> None:
    candles = make_candles([10_000.0] * 60)
    buy_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 0


# (e) BUY 부정 — 거래량 미달
def test_buy_negative_volume_low() -> None:
    candles = _buy_candles(vol_ratio=0.5, drop_pct=0.92)
    buy_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 0


# (f) BUY 경계 — Normal 강도 확인
def test_buy_boundary_normal_threshold() -> None:
    result = _eval(_buy_candles(vol_ratio=1.2, drop_pct=0.92))
    buy_sigs = [s for s in result if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 1
    assert buy_sigs[0].strength in (SignalStrength.NORMAL, SignalStrength.STRONG)


# (g) BUY 경계 — Strong 강도 확인
def test_buy_boundary_strong_threshold() -> None:
    result = _eval(_buy_candles(drop_pct=0.88))
    buy_sigs = [s for s in result if s.direction == SignalDirection.BUY]
    assert len(buy_sigs) == 1
    assert buy_sigs[0].strength == SignalStrength.STRONG


# (h) SELL Normal
def test_sell_normal() -> None:
    result = _eval(_sell_candles(vol_ratio=1.2, rise_pct=1.08))
    assert len(result) == 1
    s = result[0]
    assert s.direction == SignalDirection.SELL
    assert s.strength == SignalStrength.NORMAL
    assert s.mode == StrategyMode.MEAN_REVERSION


# (i) SELL Strong
def test_sell_strong() -> None:
    result = _eval(_sell_candles(rise_pct=1.12))
    assert len(result) == 1
    assert result[0].direction == SignalDirection.SELL
    assert result[0].strength == SignalStrength.STRONG


# (j) SELL 부정 3종
def test_sell_negative_cci_too_small() -> None:
    candles = _sell_candles(rise_pct=1.001)
    sell_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 0


def test_sell_negative_price_below_upper() -> None:
    candles = make_candles([10_000.0] * 60)
    sell_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 0


def test_sell_negative_volume_low() -> None:
    candles = _sell_candles(vol_ratio=0.5, rise_pct=1.08)
    sell_sigs = [s for s in _eval(candles) if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 0


# (k) SELL 경계 2종
def test_sell_boundary_normal_threshold() -> None:
    result = _eval(_sell_candles(vol_ratio=1.2, rise_pct=1.08))
    sell_sigs = [s for s in result if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 1
    assert sell_sigs[0].strength in (SignalStrength.NORMAL, SignalStrength.STRONG)


def test_sell_boundary_strong_threshold() -> None:
    result = _eval(_sell_candles(rise_pct=1.12))
    sell_sigs = [s for s in result if s.direction == SignalDirection.SELL]
    assert len(sell_sigs) == 1
    assert sell_sigs[0].strength == SignalStrength.STRONG


# (l) 데이터 부족 → []
def test_insufficient_data_returns_empty() -> None:
    candles = make_candles([10_000.0] * 10)
    assert _eval(candles) == []


# (m) 박스권 → []
def test_sideways_no_signal() -> None:
    candles = make_candles([10_000.0] * 60)
    assert _eval(candles) == []
