"""백테스트 결과 도메인 모델 + 지표 계산 함수 — DESIGN.md §8.5 (시그니처 변경 금지).

import 사용처:
  - engine.py (calculate_sharpe_annualized, calculate_mdd_pct)
  - M11 백테스트 HTML 리포트 (BacktestResult)
  - M15 GUI 백테스트 페이지 (BacktestEngine 통해 BacktestResult)
  - cli.py backtest 커맨드
"""

from __future__ import annotations

import statistics
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from signal_program.enums import SignalDirection, StrategyMode


class TradeRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str
    mode: StrategyMode
    direction: SignalDirection
    entry_at: datetime
    entry_price: float
    exit_at: datetime
    exit_price: float
    bars_held: int
    pnl_pct: float


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    period_from: datetime
    period_to: datetime
    trades: tuple[TradeRecord, ...]
    win_rate: float
    avg_pnl_pct: float
    cumulative_return_pct: float
    mdd_pct: float          # 음수 또는 0 (peak-to-trough drawdown)
    sharpe_annualized: float
    avg_bars_held: float


def calculate_mdd_pct(equity_curve: list[float]) -> float:
    """최대 낙폭(MDD). 부호 컨벤션: 음수 또는 0.0 (peak-to-trough drawdown).

    반환 예: -0.35 → 35% 낙폭. 낙폭 없으면 0.0.
    """
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    mdd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (eq - peak) / peak  # 음수 또는 0
            if dd < mdd:
                mdd = dd
    return mdd


def calculate_sharpe_annualized(
    trades: tuple[TradeRecord, ...],
    period_from: datetime,
    period_to: datetime,
) -> float:
    """trade-level 수익률의 연환산 Sharpe 비율.

    annualization 인자는 실측 거래 빈도(trades_per_year_observed)로 계산:
        trades_per_year = len(trades) * 365 / observation_days

    표준편차: sample std (ddof=1, statistics.stdev).

    Edge cases:
    - trades 개수 < 2 → 0.0 (std 미정의)
    - std == 0.0 → 0.0 (분모 0 방지)
    - observation_days <= 0 → 0.0 (기간 무효)
    """
    if len(trades) < 2:
        return 0.0
    observation_days = (period_to - period_from).total_seconds() / 86400
    if observation_days <= 0:
        return 0.0
    trades_per_year = len(trades) * 365.0 / observation_days
    pnls = [t.pnl_pct for t in trades]
    std = statistics.stdev(pnls)
    if std == 0.0:
        return 0.0
    return float(statistics.mean(pnls) / std * (trades_per_year**0.5))
