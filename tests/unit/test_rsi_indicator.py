"""Wilder RSI 지표 — TDD RED→GREEN (설계 v2.3 §3.3 / §7).

평활 방식: ewm(alpha=1/period, adjust=False) — Wilder 평활. SMA 방식 금지.
참조값은 Wilder ewm 정의로부터 손계산한 하드코딩 값이다(코드 출력에서 역산하지 않음).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from signal_program.indicators.rsi import rsi

# ── period=2 손계산 (alpha=0.5) ────────────────────────────────────────────
# closes : 10  11  10  11  12
# delta  :  -  +1  -1  +1  +1
# gain   :  -   1   0   1   1   (선행 NaN → ewm seed는 첫 실제 delta)
# loss   :  -   0   1   0   0
# avg_gain: NaN 1.0 0.5 0.75 0.875
# avg_loss: NaN 0.0 0.5 0.25 0.125
# rsi     : NaN 100  50   75   87.5
_CLOSES = [10.0, 11.0, 10.0, 11.0, 12.0]
_EXPECTED = [None, 100.0, 50.0, 75.0, 87.5]


def test_rsi_period2_known_values() -> None:
    out = rsi(pd.Series(_CLOSES), period=2)
    assert math.isnan(out.iloc[0])  # 첫 봉은 delta 없음 → NaN
    for i in range(1, len(_EXPECTED)):
        assert out.iloc[i] == pytest.approx(_EXPECTED[i], abs=1e-9)


def test_rsi_pure_uptrend_is_100() -> None:
    """손실이 전혀 없는 연속 상승 → RSI == 100 (정의상 참)."""
    out = rsi(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]), period=3)
    assert out.iloc[-1] == pytest.approx(100.0)


def test_rsi_pure_downtrend_is_0() -> None:
    """이득이 전혀 없는 연속 하락 → RSI == 0 (정의상 참)."""
    out = rsi(pd.Series([6.0, 5.0, 4.0, 3.0, 2.0, 1.0]), period=3)
    assert out.iloc[-1] == pytest.approx(0.0)


def test_rsi_bounds_and_length() -> None:
    closes = pd.Series([10.0 + (i % 5) for i in range(50)])
    out = rsi(closes, period=14)
    assert len(out) == len(closes)
    valid = out.dropna()
    assert (valid >= 0.0).all()
    assert (valid <= 100.0).all()


def test_rsi_default_period_14() -> None:
    """기본 period=14 동작 — 충분한 데이터에서 NaN 아님."""
    closes = pd.Series([100.0 + i * 0.5 for i in range(40)])
    out = rsi(closes)
    assert not math.isnan(out.iloc[-1])
