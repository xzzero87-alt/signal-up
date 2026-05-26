"""grid_search.py 단위 테스트 — D+7 GO/NO-GO 파라미터 비교표.

signal backtest --grid "obv_weight:0.3,0.4,0.5;buy_threshold:0.60,0.65,0.70"
→ 9개 GridCell 반환 + JSON 저장 검증.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from signal_program.backtest.metrics import BacktestResult
from signal_program.backtest.walkforward import parse_grid

_KST = ZoneInfo("Asia/Seoul")


def _make_result(cum_return: float = 0.1, sharpe: float = 1.2) -> BacktestResult:
    return BacktestResult(
        period_from=datetime(2025, 1, 1, tzinfo=_KST),
        period_to=datetime(2025, 12, 31, tzinfo=_KST),
        trades=(),
        win_rate=0.6,
        avg_pnl_pct=0.01,
        cumulative_return_pct=cum_return,
        mdd_pct=-0.05,
        sharpe_annualized=sharpe,
        avg_bars_held=5.0,
    )


def _mock_engine(result: BacktestResult) -> MagicMock:
    eng = MagicMock()
    eng.run.return_value = result
    return eng


# ── run_backtest_grid ─────────────────────────────────────────────────────────


class TestRunBacktestGrid:
    def test_returns_all_cells_for_3x3_grid(self) -> None:
        """3×3 그리드 → 9개 GridCell 반환."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("obv_weight:0.3,0.4,0.5;buy_threshold:0.60,0.65,0.70")
        result = _make_result()

        cells = run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            strategy_version="v2",
            _engine_factory=lambda p: _mock_engine(result),
        )
        assert len(cells) == 9

    def test_cell_index_starts_at_one(self) -> None:
        """cell_index는 1부터 시작해야 한다."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("obv_weight:0.3,0.4,0.5")

        cells = run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            _engine_factory=lambda p: _mock_engine(_make_result()),
        )
        assert cells[0].cell_index == 1
        assert cells[-1].cell_index == 3

    def test_v2_params_in_cell_params_dict(self) -> None:
        """V2 파라미터(obv_weight, buy_threshold)가 GridCell.params에 포함되어야 한다."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("obv_weight:0.3,0.4;buy_threshold:0.60,0.65")

        cells = run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            strategy_version="v2",
            _engine_factory=lambda p: _mock_engine(_make_result()),
        )
        for cell in cells:
            assert "obv_weight" in cell.params
            assert "buy_threshold" in cell.params

    def test_v1_params_in_cell_params_dict(self) -> None:
        """V1 파라미터(bb_std_mult)가 GridCell.params에 포함되어야 한다."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("bb_std_mult:1.5,2.0")

        cells = run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            strategy_version="v1",
            _engine_factory=lambda p: _mock_engine(_make_result()),
        )
        for cell in cells:
            assert "bb_std_mult" in cell.params

    def test_none_params_excluded_from_dict(self) -> None:
        """None인 파라미터 필드는 GridCell.params dict에서 제외되어야 한다."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("obv_weight:0.3")

        cells = run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            strategy_version="v2",
            _engine_factory=lambda p: _mock_engine(_make_result()),
        )
        assert None not in cells[0].params.values()

    def test_engine_called_once_per_cell(self) -> None:
        """엔진이 그리드 셀 수만큼 각 1회씩 호출되어야 한다."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("obv_weight:0.3,0.4,0.5")
        engines: list[MagicMock] = []

        def make_engine(p: object) -> MagicMock:
            eng = _mock_engine(_make_result())
            engines.append(eng)
            return eng

        run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            _engine_factory=make_engine,
        )
        assert len(engines) == 3
        for eng in engines:
            eng.run.assert_called_once()

    def test_handles_engine_exception_gracefully(self) -> None:
        """engine.run() 예외 시 빈 결과(0.0)로 GridCell 생성, 나머지 셀은 정상."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("obv_weight:0.3,0.4")
        call_count = 0

        def make_engine(p: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            eng = MagicMock()
            if call_count == 1:
                eng.run.side_effect = RuntimeError("캔들 부족")
            else:
                eng.run.return_value = _make_result(cum_return=0.15)
            return eng

        cells = run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            _engine_factory=make_engine,
        )
        assert len(cells) == 2
        assert cells[0].result.cumulative_return_pct == 0.0
        assert cells[1].result.cumulative_return_pct == pytest.approx(0.15)

    def test_result_metrics_preserved(self) -> None:
        """GridCell.result에 원래 BacktestResult 수치가 그대로 보존되어야 한다."""
        from signal_program.backtest.grid_search import run_backtest_grid

        grid = parse_grid("obv_weight:0.3")
        expected = _make_result(cum_return=0.42, sharpe=2.1)

        cells = run_backtest_grid(
            market="KRW-BTC",
            candles_df=pd.DataFrame(),
            param_grid=grid,
            _engine_factory=lambda p: _mock_engine(expected),
        )
        assert cells[0].result.cumulative_return_pct == pytest.approx(0.42)
        assert cells[0].result.sharpe_annualized == pytest.approx(2.1)


# ── save_grid_json ────────────────────────────────────────────────────────────


class TestSaveGridJson:
    def test_saves_json_file(self, tmp_path: Path) -> None:
        """GridCell 결과가 JSON 파일로 저장되어야 한다."""
        from signal_program.backtest.grid_search import GridCell, save_grid_json

        cells = [GridCell(cell_index=1, params={"obv_weight": 0.3}, result=_make_result())]
        path = save_grid_json(
            cells=cells,
            market="KRW-BTC",
            period_from="2025-01-01",
            period_to="2026-04-30",
            strategy_version="v2",
            grid_str="obv_weight:0.3",
            output_dir=tmp_path,
        )
        assert path.exists()
        assert path.suffix == ".json"

    def test_json_top_level_keys(self, tmp_path: Path) -> None:
        """JSON 최상위 키: market, period_from/to, strategy, cells, generated_at."""
        from signal_program.backtest.grid_search import GridCell, save_grid_json

        cells = [GridCell(cell_index=1, params={}, result=_make_result())]
        path = save_grid_json(
            cells=cells,
            market="KRW-BTC",
            period_from="2025-01-01",
            period_to="2026-04-30",
            strategy_version="v2",
            grid_str="",
            output_dir=tmp_path,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("market", "period_from", "period_to", "strategy", "cells", "generated_at"):
            assert key in data, f"최상위 키 없음: {key}"

    def test_json_cell_metrics_keys(self, tmp_path: Path) -> None:
        """각 셀의 metrics에 필수 수치 항목이 포함되어야 한다."""
        from signal_program.backtest.grid_search import GridCell, save_grid_json

        cells = [
            GridCell(
                cell_index=1,
                params={"obv_weight": 0.3, "buy_threshold": 0.60},
                result=_make_result(),
            )
        ]
        path = save_grid_json(
            cells=cells,
            market="KRW-BTC",
            period_from="2025-01-01",
            period_to="2026-04-30",
            strategy_version="v2",
            grid_str="obv_weight:0.3;buy_threshold:0.60",
            output_dir=tmp_path,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        cell = data["cells"][0]
        for key in (
            "trade_count",
            "win_rate",
            "cumulative_return_pct",
            "mdd_pct",
            "sharpe_annualized",
            "avg_pnl_pct",
            "avg_bars_held",
        ):
            assert key in cell["metrics"], f"metrics 키 없음: {key}"

    def test_json_filename_contains_market_and_strategy(self, tmp_path: Path) -> None:
        """파일명에 시장명(KRW_BTC)과 전략 버전(v2)이 포함되어야 한다."""
        from signal_program.backtest.grid_search import GridCell, save_grid_json

        cells = [GridCell(cell_index=1, params={}, result=_make_result())]
        path = save_grid_json(
            cells=cells,
            market="KRW-BTC",
            period_from="2025-01-01",
            period_to="2026-04-30",
            strategy_version="v2",
            grid_str="",
            output_dir=tmp_path,
        )
        assert "v2" in path.name
        assert "KRW_BTC" in path.name

    def test_output_dir_created_if_not_exists(self, tmp_path: Path) -> None:
        """output_dir이 없으면 자동 생성해야 한다."""
        from signal_program.backtest.grid_search import GridCell, save_grid_json

        new_dir = tmp_path / "state" / "backtest"
        assert not new_dir.exists()
        cells = [GridCell(cell_index=1, params={}, result=_make_result())]
        save_grid_json(
            cells=cells,
            market="KRW-BTC",
            period_from="2025-01-01",
            period_to="2026-04-30",
            strategy_version="v2",
            grid_str="",
            output_dir=new_dir,
        )
        assert new_dir.exists()
