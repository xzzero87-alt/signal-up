"""M2 횡단면 모멘텀(12-1, top10, 월간 리밸런스) — ADR-0031.

기존 봉단위 Strategy Protocol(DESIGN.md §8.3)과 독립된 신규 모듈. §8.1~8.5 시그니처는
건드리지 않는다. 로직은 scripts/round2_m2_backtest.py(build_universes/run_m2)와 동일해야 한다.
"""

from __future__ import annotations

from signal_program.momentum.core import (
    build_universe,
    diff_portfolio,
    pending_rebalance_asof,
    select_top10,
)

__all__ = [
    "build_universe",
    "diff_portfolio",
    "pending_rebalance_asof",
    "select_top10",
]
