"""워크포워드 파라미터 검증 엔진 — DESIGN.md §6.4.

§6.4 워크포워드:
  - 8개월 학습 / 2개월 검증 슬라이딩 4구간
  - 검증 구간 결과만 "out-of-sample" 합본
  - 그리드 서치 목적함수: validate_result.sharpe_annualized 최대

모델 (walkforward.py 안에서만 정의 — DESIGN §8.5 영역 침범 금지):
  - StrategyParams  : 그리드 서치 대상 파라미터
  - WalkforwardFold : 한 fold의 학습/검증 결과
  - WalkforwardResult : 전체 워크포워드 결과

import 사용처:
  - cli.py walkforward 커맨드
  - report.py walkforward_render_html
  - M15 GUI 백테스트 페이지 (예정)
"""

from __future__ import annotations

import itertools
import statistics
from collections.abc import Callable  # noqa: TC003
from datetime import datetime  # noqa: TC003
from pathlib import Path  # noqa: TC003
from typing import Any

import pandas as pd
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, ConfigDict, field_validator

from signal_program.backtest.engine import BacktestEngine
from signal_program.backtest.metrics import (
    BacktestResult,
    TradeRecord,
    calculate_mdd_pct,
    calculate_sharpe_annualized,
)

# ── 예외 ─────────────────────────────────────────────────────────────────────


class WalkforwardDataError(Exception):
    """워크포워드 기간 또는 데이터 부족 오류."""


# ── StrategyParams ────────────────────────────────────────────────────────────


class StrategyParams(BaseModel):
    """그리드 서치 대상 파라미터. 기본값은 Settings 기본값과 일치.

    필드 추가는 follow-up PR. 현재는 BB·CCI·거래량 핵심 3개.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bb_std_mult: float = 2.0
    cci_threshold_normal: int = 100
    volume_ratio_min_a: float = 1.0

    @field_validator("bb_std_mult")
    @classmethod
    def _bb_std_mult_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"bb_std_mult must be > 0, got {v}")
        return v

    @field_validator("cci_threshold_normal")
    @classmethod
    def _cci_threshold_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"cci_threshold_normal must be > 0, got {v}")
        return v

    @field_validator("volume_ratio_min_a")
    @classmethod
    def _volume_ratio_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"volume_ratio_min_a must be > 0, got {v}")
        return v


# ── 도메인 모델 ───────────────────────────────────────────────────────────────


class WalkforwardFold(BaseModel):
    """한 fold의 학습 + 검증 결과."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    fold_index: int
    train_period_from: datetime
    train_period_to: datetime
    validate_period_from: datetime
    validate_period_to: datetime
    best_params: StrategyParams
    train_result: BacktestResult
    validate_result: BacktestResult


class WalkforwardResult(BaseModel):
    """전체 워크포워드 결과 (합본 out-of-sample 포함)."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    period_from: datetime
    period_to: datetime
    train_window_days: int
    validate_window_days: int
    folds: tuple[WalkforwardFold, ...]
    out_of_sample_combined: BacktestResult


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────


def _generate_folds(
    period_from: datetime,
    period_to: datetime,
    train_months: int,
    validate_months: int,
) -> list[tuple[datetime, datetime, datetime, datetime]]:
    """(train_from, train_to, validate_from, validate_to) 리스트 반환.

    period_to는 exclusive end (마지막 날 + 1일).
    validate_to <= period_to 인 fold만 포함.
    """
    folds: list[tuple[datetime, datetime, datetime, datetime]] = []
    current_from = period_from

    while True:
        train_to = current_from + relativedelta(months=train_months)
        validate_to = train_to + relativedelta(months=validate_months)

        if validate_to > period_to:
            break

        folds.append((current_from, train_to, train_to, validate_to))
        current_from += relativedelta(months=validate_months)

    if not folds:
        raise WalkforwardDataError(
            f"기간이 너무 짧습니다. train={train_months}개월 + validate={validate_months}개월 = "
            f"{train_months + validate_months}개월 이상 필요. "
            f"제공된 기간: {period_from:%Y-%m-%d} ~ {period_to:%Y-%m-%d}"
        )

    return folds


def _params_to_strategy(params: StrategyParams) -> Any:
    """StrategyParams → BbCciStrategy. 나머지 파라미터는 기본값 유지."""
    from signal_program.strategies.bb_cci import BbCciStrategy

    return BbCciStrategy(
        bb_std_mult=params.bb_std_mult,
        cci_threshold_normal=params.cci_threshold_normal,
        volume_ratio_min_a=params.volume_ratio_min_a,
    )


def _load_candles_df(
    market: str,
    period_from: datetime,
    period_to: datetime,
    cache_root: Path,
) -> pd.DataFrame:
    """parquet 캐시에서 특정 기간 캔들을 DataFrame으로 로드한다."""
    from signal_program.backtest.candles_io import load_candles

    all_candles = []
    cur = period_from.replace(day=1)
    while cur < period_to:
        month_str = cur.strftime("%Y-%m")
        path = cache_root / market / "60" / f"{month_str}.parquet"
        if path.exists():
            all_candles.extend(load_candles(path))
        cur = (cur + relativedelta(months=1)).replace(day=1)

    candles = [c for c in all_candles if period_from <= c.opened_at < period_to]
    candles.sort(key=lambda c: c.opened_at)

    if not candles:
        return pd.DataFrame()

    return pd.DataFrame([c.model_dump() for c in candles])


def _build_result(
    trades: tuple[TradeRecord, ...],
    period_from: datetime,
    period_to: datetime,
) -> BacktestResult:
    """TradeRecord 튜플로 BacktestResult를 조립한다."""
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

    equity = 1.0
    equity_curve = [1.0]
    for p in pnls:
        equity *= 1 + p
        equity_curve.append(equity)

    return BacktestResult(
        period_from=period_from,
        period_to=period_to,
        trades=trades,
        win_rate=wins / len(trades),
        avg_pnl_pct=statistics.mean(pnls),
        cumulative_return_pct=equity - 1.0,
        mdd_pct=calculate_mdd_pct(equity_curve),
        sharpe_annualized=calculate_sharpe_annualized(trades, period_from, period_to),
        avg_bars_held=sum(t.bars_held for t in trades) / len(trades),
    )


def _grid_search(
    market: str,
    candles_df: pd.DataFrame,
    param_grid: tuple[StrategyParams, ...],
    engine_factory: Callable[[StrategyParams], Any],
    objective: Callable[[BacktestResult], float],
) -> tuple[StrategyParams, BacktestResult]:
    """그리드 서치. 최적 파라미터와 학습 결과를 반환한다.

    동점 시 그리드 순서 첫 번째 선택 (결정성 보장).
    """
    best_params = param_grid[0]
    best_score = float("-inf")
    best_result: BacktestResult | None = None

    for params in param_grid:
        engine = engine_factory(params)
        try:
            result = engine.run(market, candles_df)
        except Exception:
            result = None

        score = objective(result) if result is not None else float("-inf")
        if score > best_score:
            best_score = score
            best_params = params
            best_result = result

    if best_result is None:
        # 모든 파라미터가 실패한 경우 기본 빈 결과
        best_result = BacktestResult(
            period_from=datetime.min,
            period_to=datetime.max,
            trades=(),
            win_rate=0.0,
            avg_pnl_pct=0.0,
            cumulative_return_pct=0.0,
            mdd_pct=0.0,
            sharpe_annualized=0.0,
            avg_bars_held=0.0,
        )

    return best_params, best_result


def parse_grid(grid_str: str) -> tuple[StrategyParams, ...]:
    """'bb_std_mult:1.5,2.0,2.5;cci_threshold_normal:80,100' → StrategyParams 튜플.

    단일 파라미터면 단순 리스트. 복수면 itertools.product로 조합.
    """
    field_values: dict[str, list[str]] = {}

    for part in grid_str.split(";"):
        part = part.strip()
        if not part:
            continue
        key, _, vals = part.partition(":")
        field_values[key.strip()] = [v.strip() for v in vals.split(",") if v.strip()]

    if not field_values:
        return (StrategyParams(),)

    keys = list(field_values.keys())
    value_lists = [field_values[k] for k in keys]

    params_list = []
    for combo in itertools.product(*value_lists):
        kwargs: dict[str, Any] = {}
        for key, val in zip(keys, combo, strict=True):
            if key == "cci_threshold_normal":
                kwargs[key] = int(float(val))
            else:
                kwargs[key] = float(val)
        params_list.append(StrategyParams(**kwargs))

    return tuple(params_list)


# ── WalkforwardEngine ─────────────────────────────────────────────────────────


def _default_objective(r: BacktestResult) -> float:
    return r.sharpe_annualized


class WalkforwardEngine:
    """8개월 학습 / 2개월 검증 슬라이딩 워크포워드 엔진.

    backtest_engine은 fee_rate / slippage_rate / max_holding_bars 템플릿으로 사용.
    각 파라미터 조합마다 새 BacktestEngine 인스턴스를 생성한다.
    """

    def __init__(
        self,
        *,
        backtest_engine: BacktestEngine,
        candles_cache_root: Path,
        param_grid: tuple[StrategyParams, ...],
        objective: Callable[[BacktestResult], float] | None = None,
    ) -> None:
        self.backtest_engine = backtest_engine
        self.candles_cache_root = candles_cache_root
        self.param_grid = param_grid
        self.objective: Callable[[BacktestResult], float] = (
            objective if objective is not None else _default_objective
        )

    def _engine_factory(self, params: StrategyParams) -> BacktestEngine:
        return BacktestEngine(
            strategy=_params_to_strategy(params),
            fee_rate=self.backtest_engine.fee_rate,
            slippage_rate=self.backtest_engine.slippage_rate,
            max_holding_bars=self.backtest_engine.max_holding_bars,
        )

    def run(
        self,
        *,
        market: str,
        period_from: datetime,
        period_to: datetime,
        train_months: int = 8,
        validate_months: int = 2,
    ) -> WalkforwardResult:
        """워크포워드 실행.

        슬라이딩 윈도우 → 그리드 서치 (학습) → 최적 파라미터로 검증 → OOS 합본.
        """
        fold_windows = _generate_folds(period_from, period_to, train_months, validate_months)

        folds: list[WalkforwardFold] = []

        for fold_idx, (train_from, train_to, val_from, val_to) in enumerate(fold_windows):
            train_df = _load_candles_df(market, train_from, train_to, self.candles_cache_root)

            best_params, best_train_result = _grid_search(
                market, train_df, self.param_grid, self._engine_factory, self.objective
            )
            # 빈 결과인 경우 기간 보정
            if not best_train_result.trades:
                best_train_result = _build_result((), train_from, train_to)

            # 검증 구간 (최적 파라미터 적용)
            val_df = _load_candles_df(market, val_from, val_to, self.candles_cache_root)
            val_engine = self._engine_factory(best_params)
            try:
                val_result = val_engine.run(market, val_df)
            except Exception:
                val_result = _build_result((), val_from, val_to)

            folds.append(
                WalkforwardFold(
                    fold_index=fold_idx,
                    train_period_from=train_from,
                    train_period_to=train_to,
                    validate_period_from=val_from,
                    validate_period_to=val_to,
                    best_params=best_params,
                    train_result=best_train_result,
                    validate_result=val_result,
                )
            )

        # OOS 합본 — validate trades만 (train trades 배제 = data leakage 방지)
        all_val_trades: list[TradeRecord] = []
        for fold in folds:
            all_val_trades.extend(fold.validate_result.trades)
        all_val_trades.sort(key=lambda t: t.entry_at)

        oos_from = folds[0].validate_period_from
        oos_to = folds[-1].validate_period_to
        oos_combined = _build_result(tuple(all_val_trades), oos_from, oos_to)

        train_window_days = (folds[0].train_period_to - folds[0].train_period_from).days
        validate_window_days = (folds[0].validate_period_to - folds[0].validate_period_from).days

        return WalkforwardResult(
            period_from=period_from,
            period_to=period_to,
            train_window_days=train_window_days,
            validate_window_days=validate_window_days,
            folds=tuple(folds),
            out_of_sample_combined=oos_combined,
        )
