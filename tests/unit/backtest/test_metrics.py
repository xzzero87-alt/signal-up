"""metrics.py 모듈 단위 테스트 — Sharpe annualization + MDD 부호 컨벤션.

Phase 1 RED: calculate_sharpe_annualized · calculate_mdd_pct 미존재 → ImportError
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from signal_program.backtest.metrics import (
    TradeRecord,
    calculate_mdd_pct,
    calculate_sharpe_annualized,
)
from signal_program.enums import SignalDirection, StrategyMode

_KST = ZoneInfo("Asia/Seoul")
_BASE = datetime(2025, 1, 1, 0, 0, 0, tzinfo=_KST)


def _trade(pnl: float, bars: int = 12) -> TradeRecord:
    return TradeRecord(
        market="KRW-BTC",
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        entry_at=_BASE,
        entry_price=50_000_000.0,
        exit_at=_BASE + timedelta(hours=bars),
        exit_price=50_000_000.0 * (1.0 + pnl),
        bars_held=bars,
        pnl_pct=pnl,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Sharpe annualization — trade-level 수익률 + 실측 거래 빈도
# ══════════════════════════════════════════════════════════════════════════════

def test_sharpe_uses_trade_frequency_annualization() -> None:
    period_from = _BASE
    period_to = datetime(2026, 1, 1, tzinfo=_KST)  # 365 days

    pnls = [0.01] * 60 + [-0.005] * 40  # 100 trades, known distribution
    trades = tuple(_trade(p) for p in pnls)

    # 분석적 기댓값 계산
    obs_days = (period_to - period_from).total_seconds() / 86400
    t_per_yr = len(trades) * 365.0 / obs_days
    std = statistics.stdev(pnls)
    expected = statistics.mean(pnls) / std * (t_per_yr**0.5)

    result = calculate_sharpe_annualized(trades, period_from, period_to)
    assert result == pytest.approx(expected, rel=1e-6)


def test_sharpe_with_observation_window_two_years() -> None:
    period_from = _BASE
    period_to_1yr = datetime(2026, 1, 1, tzinfo=_KST)
    period_to_2yr = datetime(2027, 1, 1, tzinfo=_KST)

    pnls = [0.01] * 60 + [-0.005] * 40
    trades = tuple(_trade(p) for p in pnls)

    sharpe_1yr = calculate_sharpe_annualized(trades, period_from, period_to_1yr)
    sharpe_2yr = calculate_sharpe_annualized(trades, period_from, period_to_2yr)

    # trades_per_year 절반 → |Sharpe| 비율 = 1/√2
    assert sharpe_2yr == pytest.approx(sharpe_1yr / (2**0.5), rel=1e-4)


def test_sharpe_zero_when_single_trade() -> None:
    trades = (_trade(0.01),)
    period_to = datetime(2026, 1, 1, tzinfo=_KST)
    assert calculate_sharpe_annualized(trades, _BASE, period_to) == 0.0


def test_sharpe_zero_when_std_is_zero() -> None:
    # 모든 거래 수익 동일 → std = 0 → Sharpe = 0
    trades = tuple(_trade(0.01) for _ in range(10))
    period_to = datetime(2026, 1, 1, tzinfo=_KST)
    assert calculate_sharpe_annualized(trades, _BASE, period_to) == 0.0


def test_sharpe_zero_when_observation_window_invalid() -> None:
    # period_to <= period_from → observation_days <= 0
    trades = tuple(_trade(p) for p in [0.01] * 5 + [-0.005] * 5)
    assert calculate_sharpe_annualized(trades, _BASE, _BASE) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# MDD 부호 컨벤션 — 음수 또는 0 (peak-to-trough drawdown)
# ══════════════════════════════════════════════════════════════════════════════

def test_mdd_negative_for_losing_equity_curve() -> None:
    # 1.0 → 0.95 → 0.90 → 0.92 → 0.88 → 0.93
    # 최대 낙폭: (0.88 - 1.0) / 1.0 = -0.12
    equity = [1.0, 0.95, 0.90, 0.92, 0.88, 0.93]
    result = calculate_mdd_pct(equity)
    assert result < 0.0
    assert result == pytest.approx(-0.12, rel=1e-6)


def test_mdd_zero_for_monotonic_gains() -> None:
    equity = [1.0, 1.05, 1.10, 1.15, 1.20]
    assert calculate_mdd_pct(equity) == 0.0


def test_mdd_empty_returns_zero() -> None:
    assert calculate_mdd_pct([]) == 0.0
