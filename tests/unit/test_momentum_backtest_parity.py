"""select_top10 vs scripts/round2_m2_backtest.py 선정 결과 패리티 (ADR-0031).

실 캐시(data/candles/, scripts/round2_pool.csv) 필요 — slow.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

from signal_program.momentum.core import (
    _target_month,
    build_universe,
    pending_rebalance_asof,
    select_top10,
)

pytestmark = pytest.mark.slow

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "round2_m2_backtest.py"


def _load_round2_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("round2_m2_backtest", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["round2_m2_backtest"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.mark.timeout(300)  # 148종 parquet 로드 — I/O 부하 시 기본 60s 초과, 검증 내용 불변
@pytest.mark.skipif(
    not (_REPO_ROOT / "data" / "candles").exists(),
    reason="실 캔들 캐시 없음 — 로컬 데이터 필요",
)
def test_select_top10_matches_round2_reference_2025_12_30() -> None:
    """2025-12-30 시점 top10이 round2_m2_backtest.py의 선정과 동일해야 한다."""
    import os

    os.chdir(_REPO_ROOT)  # round2_m2_backtest.py의 상대경로(BASE/POOL) 기준
    ref = _load_round2_module()

    px, qv = ref.load_matrix()
    pool_codes = [c for c in pd.read_csv(ref.POOL, dtype=str)["code"] if c in px.columns]
    ref_universes = ref.build_universes(qv, pool_codes)
    ref_uni_2025 = ref_universes[2025]

    # momentum/core.build_universe로 동일 유니버스 재현
    my_uni_2025 = build_universe(qv[pool_codes], year=2025, top_n=50)
    assert set(my_uni_2025) == set(ref_uni_2025)

    asof = pd.Timestamp("2025-12-30")
    top = select_top10(px, my_uni_2025, asof, n=10)
    my_top_codes = set(top["code"])

    # 레퍼런스 선정: run_m2()와 동일한 모멘텀 계산을 12월 마감일 기준으로 직접 재현
    idx = px.index.get_indexer([asof], method="ffill")[0]
    mom = (px.iloc[idx - 21] / px.iloc[idx - 252] - 1)[ref_uni_2025].dropna()
    ref_top_codes = set(mom.nlargest(10).index)

    assert my_top_codes == ref_top_codes


@pytest.mark.timeout(300)  # 148종 로드 + 전체기간 day-by-day 시뮬 — I/O 부하 시 60s 초과
@pytest.mark.skipif(
    not (_REPO_ROOT / "data" / "candles").exists(),
    reason="실 캔들 캐시 없음 — 로컬 데이터 필요",
)
def test_live_fired_asof_set_matches_backtest_month_ends() -> None:
    """발화일 패리티 — 최우선 회귀 테스트 (마일스톤19 Evaluator가 발견한 결함).

    이 테스트가 없어서 "12월 리밸런스 영구 누락" 버그가 검증을 통과했었다.
    day-by-day로 실제 라이브 조건(오늘까지만 관측된 캔들)을 재현하며
    pending_rebalance_asof를 매일 호출해 발화한 asof 집합을 모으고,
    round2_m2_backtest.month_ends()가 계산하는 "완결된 달"의 asof 집합과
    정확히 일치하는지 확인한다.
    """
    import os

    os.chdir(_REPO_ROOT)
    ref = _load_round2_module()
    px, _ = ref.load_matrix()

    all_ends = ref.month_ends(px.index)
    last_date = px.index.max()
    complete_target = _target_month(last_date.date())
    reference_ends = {
        pd.Timestamp(d).normalize() for d in all_ends if (d.year, d.month) <= complete_target
    }

    fired: set[pd.Timestamp] = set()
    last_rebalanced_asof = None
    for day in pd.date_range(px.index.min().normalize(), px.index.max().normalize(), freq="D"):
        today = day.date()
        observed = pd.DatetimeIndex(px.index[px.index <= day])
        asof = pending_rebalance_asof(observed, today, last_rebalanced_asof)
        if asof is not None:
            fired.add(asof.normalize())
            last_rebalanced_asof = asof.date()

    assert fired == reference_ends


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "slow"])
