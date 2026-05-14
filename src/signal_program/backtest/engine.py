"""백테스트 엔진 — DESIGN.md §6 시뮬레이션 규칙.

§6.1 시뮬레이션 규칙:
  - 봉 단위 시뮬레이터. 직전봉 시그널 → 다음봉 시가 진입
  - 단일 종목, 단일 방향(BUY만), 1회 1포지션
  - 청산: max_holding_bars 보유 또는 BB 중심선(entry 시점 기준) 도달 중 빠른 쪽
  - 미청산 포지션은 마지막 봉 close로 강제 청산

§6.2 비용 모델:
  - 진입·청산 각각 (fee_rate + slippage_rate) 적용
  - pnl_pct = exit*(1-cost) / (entry*(1+cost)) - 1

import 사용처:
  - cli.py backtest 커맨드
  - M15 GUI 백테스트 페이지
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from signal_program.backtest.metrics import BacktestResult

if TYPE_CHECKING:
    from signal_program.strategies.base import Strategy


class BacktestEngine:
    """봉 단위 백테스트 시뮬레이터."""

    def __init__(
        self,
        strategy: Strategy,
        fee_rate: float = 0.0005,
        slippage_rate: float = 0.0005,
        max_holding_bars: int = 24,
    ) -> None:
        self.strategy = strategy
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.max_holding_bars = max_holding_bars

    def run(self, market: str, candles_df: pd.DataFrame) -> BacktestResult:
        """백테스트 실행. 전체 시뮬레이션 결과를 BacktestResult로 반환."""
        raise NotImplementedError
