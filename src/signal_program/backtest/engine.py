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

import statistics
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Any

import pandas as pd

from signal_program.backtest.metrics import BacktestResult, TradeRecord
from signal_program.enums import SignalDirection

if TYPE_CHECKING:
    from signal_program.strategies.base import Strategy


def _to_dt(val: Any) -> datetime:
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    assert isinstance(val, datetime)
    return val


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
        if len(candles_df) == 0:
            raise ValueError("candles_df must not be empty")

        trades: list[TradeRecord] = []
        position: dict[str, Any] | None = None

        for i in range(len(candles_df)):
            if position is None:
                signals = self.strategy.evaluate(market, candles_df.iloc[: i + 1])
                buy_sig = next(
                    (s for s in signals if s.direction == SignalDirection.BUY), None
                )
                if buy_sig is not None and i + 1 < len(candles_df):
                    position = {
                        "signal_bar_idx": i,
                        "entry_price": float(candles_df.iloc[i + 1]["open"]),
                        "entry_at": candles_df.iloc[i + 1]["opened_at"],
                        "bb_middle": buy_sig.indicators.bb_middle,
                        "mode": buy_sig.mode,
                        "direction": buy_sig.direction,
                    }
            else:
                bars_held = i - position["signal_bar_idx"]
                close = float(candles_df.iloc[i]["close"])
                bb_middle: float = position["bb_middle"]
                should_exit = bars_held >= self.max_holding_bars or close >= bb_middle

                if should_exit:
                    opened_at = candles_df.iloc[i]["opened_at"]
                    trades.append(self._make_trade(position, close, opened_at, bars_held, market))
                    position = None

        # 미청산 포지션 → 마지막 봉 강제 청산
        if position is not None:
            last = len(candles_df) - 1
            bars_held = last - position["signal_bar_idx"]
            close = float(candles_df.iloc[last]["close"])
            last_opened_at = candles_df.iloc[last]["opened_at"]
            trades.append(self._make_trade(position, close, last_opened_at, bars_held, market))

        return self._aggregate(market, candles_df, trades)

    def _make_trade(
        self,
        position: dict[str, Any],
        exit_close: float,
        exit_opened_at: Any,
        bars_held: int,
        market: str,
    ) -> TradeRecord:
        cost = self.fee_rate + self.slippage_rate
        entry_price: float = position["entry_price"]
        denom = entry_price * (1 + cost)
        pnl_pct = exit_close * (1 - cost) / denom - 1 if denom != 0.0 else 0.0
        return TradeRecord(
            market=market,
            mode=position["mode"],
            direction=position["direction"],
            entry_at=_to_dt(position["entry_at"]),
            entry_price=entry_price,
            exit_at=_to_dt(exit_opened_at),
            exit_price=exit_close,
            bars_held=bars_held,
            pnl_pct=pnl_pct,
        )

    def _aggregate(
        self, market: str, candles_df: pd.DataFrame, trades: list[TradeRecord]
    ) -> BacktestResult:
        period_from = _to_dt(candles_df.iloc[0]["opened_at"])
        period_to = _to_dt(candles_df.iloc[-1]["opened_at"])

        if not trades:
            return BacktestResult(
                period_from=period_from,
                period_to=period_to,
                trades=(),
                win_rate=0.0,
                avg_pnl_pct=0.0,
                cumulative_return_pct=0.0,
                mdd_pct=0.0,
                sharpe_annualized=0.0,
                avg_bars_held=0.0,
            )

        pnls = [t.pnl_pct for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls)
        avg_pnl = sum(pnls) / len(pnls)

        # 복리 누적 수익
        equity = 1.0
        equity_curve = [1.0]
        for p in pnls:
            equity *= 1 + p
            equity_curve.append(equity)
        cumulative_return_pct = equity - 1.0

        # MDD
        peak = equity_curve[0]
        mdd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > mdd:
                mdd = dd

        # 샤프 (연환산, 1h봉 기준 8760h/년)
        if len(pnls) < 2:
            sharpe = 0.0
        else:
            std = statistics.stdev(pnls)
            sharpe = (
                0.0
                if std == 0.0
                else (statistics.mean(pnls) / std) * (8760**0.5)
            )

        avg_bars = sum(t.bars_held for t in trades) / len(trades)

        return BacktestResult(
            period_from=period_from,
            period_to=period_to,
            trades=tuple(trades),
            win_rate=win_rate,
            avg_pnl_pct=avg_pnl,
            cumulative_return_pct=cumulative_return_pct,
            mdd_pct=mdd,
            sharpe_annualized=sharpe,
            avg_bars_held=avg_bars,
        )
