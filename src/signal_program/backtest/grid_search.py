"""백테스트 파라미터 그리드 서치 — D+7 GO/NO-GO 비교표 산출.

signal backtest --grid "obv_weight:0.3,0.4,0.5;buy_threshold:0.60,0.65,0.70"
→ 9개 GridCell 실행 → Rich 비교표 출력 + JSON 저장.

import 사용처:
  - cli.py backtest --grid 옵션
  - tests/unit/backtest/test_grid_search.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pandas as pd

from signal_program.backtest.engine import BacktestEngine
from signal_program.backtest.metrics import BacktestResult


@dataclass(frozen=True)
class GridCell:
    """단일 파라미터 조합의 백테스트 결과."""

    cell_index: int  # 1-based
    params: dict[str, float]
    result: BacktestResult


def run_backtest_grid(
    market: str,
    candles_df: pd.DataFrame,
    param_grid: tuple[Any, ...],
    strategy_version: str = "v1",
    base_settings: Any = None,
    _engine_factory: Callable[[Any], BacktestEngine] | None = None,
) -> list[GridCell]:
    """파라미터 그리드 전체 백테스트 실행 → GridCell 리스트 반환.

    _engine_factory: 테스트 주입용 (None → 실제 전략 생성).
    """
    from signal_program.backtest.walkforward import _params_to_strategy

    def _default_factory(params: Any) -> BacktestEngine:
        strategy = _params_to_strategy(params, strategy_version, base_settings)
        return BacktestEngine(strategy=strategy)

    factory = _engine_factory if _engine_factory is not None else _default_factory

    cells: list[GridCell] = []
    for idx, params in enumerate(param_grid, start=1):
        engine = factory(params)
        try:
            result = engine.run(market, candles_df)
        except Exception:
            result = _empty_result()

        # None 필드 제외 — V2 그리드에서 V1 필드(None), V1 그리드에서 V2 필드(None)
        params_dict: dict[str, float] = {
            k: v for k, v in params.model_dump().items() if v is not None
        }
        cells.append(GridCell(cell_index=idx, params=params_dict, result=result))

    return cells


def _empty_result() -> BacktestResult:
    """캔들 부족 등 engine.run() 실패 시 반환하는 빈 결과."""
    return BacktestResult(
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


def save_grid_json(
    *,
    cells: list[GridCell],
    market: str,
    period_from: str,
    period_to: str,
    strategy_version: str,
    grid_str: str,
    output_dir: Path,
) -> Path:
    """GridCell 결과를 JSON으로 저장하고 파일 경로를 반환한다.

    저장 경로: {output_dir}/{strategy}_grid_{market}_{YYYYMMDD_HHMMSS}.json
    """
    kst = ZoneInfo("Asia/Seoul")
    ts = datetime.now(tz=kst).strftime("%Y%m%d_%H%M%S")
    safe_market = market.replace("-", "_")
    filename = f"{strategy_version}_grid_{safe_market}_{ts}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename

    data: dict[str, Any] = {
        "market": market,
        "period_from": period_from,
        "period_to": period_to,
        "strategy": strategy_version,
        "grid_str": grid_str,
        "generated_at": datetime.now(tz=kst).isoformat(),
        "cells": [
            {
                "cell": cell.cell_index,
                "params": cell.params,
                "metrics": {
                    "trade_count": len(cell.result.trades),
                    "win_rate": round(cell.result.win_rate, 4),
                    "avg_pnl_pct": round(cell.result.avg_pnl_pct, 4),
                    "cumulative_return_pct": round(cell.result.cumulative_return_pct, 4),
                    "mdd_pct": round(cell.result.mdd_pct, 4),
                    "sharpe_annualized": round(cell.result.sharpe_annualized, 4),
                    "avg_bars_held": round(cell.result.avg_bars_held, 1),
                },
            }
            for cell in cells
        ],
    }

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
