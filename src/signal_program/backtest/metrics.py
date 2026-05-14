"""백테스트 결과 도메인 모델 — DESIGN.md §8.5 (시그니처 변경 금지).

import 사용처:
  - M11 백테스트 HTML 리포트 (BacktestResult)
  - M15 GUI 백테스트 페이지 (BacktestEngine 통해 BacktestResult)
  - cli.py backtest 커맨드
"""

from __future__ import annotations

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
    mdd_pct: float
    sharpe_annualized: float
    avg_bars_held: float
