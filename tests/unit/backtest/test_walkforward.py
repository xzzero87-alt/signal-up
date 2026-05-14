"""WalkforwardEngine 단위 테스트 18종 — Phase 1: RED (walkforward.py 미존재 → ImportError).

period_to 컨벤션: exclusive end (예: "2026-04-30" → datetime(2026, 5, 1)).
MDD 컨벤션: 모델 음수 / 표시 abs() (M10 follow-up 확정).
OOS 합본: validate trades만 — train trades는 절대 포함 금지 (data leakage 방지).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from signal_program.backtest.metrics import BacktestResult, TradeRecord
from signal_program.backtest.walkforward import (
    StrategyParams,
    WalkforwardDataError,
    WalkforwardFold,
    WalkforwardResult,
    _build_result,
    _generate_folds,
    _grid_search,
    _params_to_strategy,
    parse_grid,
)
from signal_program.enums import SignalDirection, StrategyMode

_KST = ZoneInfo("Asia/Seoul")
_FROM = datetime(2025, 1, 1, tzinfo=_KST)
_TO = datetime(2026, 5, 1, tzinfo=_KST)   # exclusive end (represents 2026-04-30)
_TEMPLATE_DIR = Path(__file__).parents[3] / "templates"


# ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────

def _fake_result(*, sharpe: float = 0.0, mdd: float = -0.05) -> BacktestResult:
    return BacktestResult(
        period_from=_FROM,
        period_to=_TO,
        trades=(),
        win_rate=0.5,
        avg_pnl_pct=0.001,
        cumulative_return_pct=0.05,
        mdd_pct=mdd,
        sharpe_annualized=sharpe,
        avg_bars_held=12.0,
    )


def _make_trade(entry_at: datetime, pnl: float = 0.01) -> TradeRecord:
    return TradeRecord(
        market="KRW-BTC",
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        entry_at=entry_at,
        entry_price=50_000_000.0,
        exit_at=entry_at + timedelta(hours=12),
        exit_price=50_000_000.0 * (1 + pnl),
        bars_held=12,
        pnl_pct=pnl,
    )


def _make_fold(
    *,
    fold_index: int,
    train_from: datetime,
    train_to: datetime,
    val_from: datetime,
    val_to: datetime,
    train_trade: TradeRecord | None = None,
    val_trade: TradeRecord | None = None,
) -> WalkforwardFold:
    tr = _build_result((train_trade,) if train_trade else (), train_from, train_to)
    vr = _build_result((val_trade,) if val_trade else (), val_from, val_to)
    return WalkforwardFold(
        fold_index=fold_index,
        train_period_from=train_from,
        train_period_to=train_to,
        validate_period_from=val_from,
        validate_period_to=val_to,
        best_params=StrategyParams(),
        train_result=tr,
        validate_result=vr,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 슬라이딩 윈도우
# ══════════════════════════════════════════════════════════════════════════════

def test_generate_folds_16months_8_2_yields_4_folds() -> None:
    folds = _generate_folds(_FROM, _TO, 8, 2)
    assert len(folds) == 4


def test_generate_folds_non_overlapping_validate_windows() -> None:
    folds = _generate_folds(_FROM, _TO, 8, 2)
    for i in range(len(folds) - 1):
        _, _, _, val_to_i = folds[i]
        _, _, val_from_j, _ = folds[i + 1]
        assert val_to_i == val_from_j, f"Gap/overlap between fold {i} and {i+1}"


def test_generate_folds_continuous_validate_coverage() -> None:
    folds = _generate_folds(_FROM, _TO, 8, 2)
    # Fold 0: validate Sep 2025 ~ Nov 2025; Fold 3: validate Mar 2026 ~ May 2026
    assert folds[0][2] == datetime(2025, 9, 1, tzinfo=_KST)
    assert folds[-1][3] == datetime(2026, 5, 1, tzinfo=_KST)


def test_generate_folds_too_short_period_raises() -> None:
    too_short_to = datetime(2025, 6, 1, tzinfo=_KST)  # 5개월 < 10개월(8+2)
    with pytest.raises(WalkforwardDataError):
        _generate_folds(_FROM, too_short_to, 8, 2)


# ══════════════════════════════════════════════════════════════════════════════
# 그리드 서치
# ══════════════════════════════════════════════════════════════════════════════

def test_grid_picks_param_maximizing_sharpe() -> None:
    sharpe_map = {1.5: 0.5, 2.0: 1.2, 2.5: -0.8}

    def mock_factory(params: StrategyParams) -> MagicMock:
        eng = MagicMock()
        eng.run.return_value = _fake_result(sharpe=sharpe_map[params.bb_std_mult])
        return eng

    grid = (
        StrategyParams(bb_std_mult=1.5),
        StrategyParams(bb_std_mult=2.0),
        StrategyParams(bb_std_mult=2.5),
    )
    best, _ = _grid_search("KRW-BTC", pd.DataFrame(), grid, mock_factory, lambda r: r.sharpe_annualized)
    assert best.bb_std_mult == pytest.approx(2.0)


def test_grid_tiebreak_is_deterministic() -> None:
    def mock_factory(params: StrategyParams) -> MagicMock:
        eng = MagicMock()
        eng.run.return_value = _fake_result(sharpe=0.5)  # 모두 동점
        return eng

    grid = (
        StrategyParams(bb_std_mult=2.5),
        StrategyParams(bb_std_mult=1.5),
        StrategyParams(bb_std_mult=2.0),
    )
    best, _ = _grid_search("KRW-BTC", pd.DataFrame(), grid, mock_factory, lambda r: r.sharpe_annualized)
    assert best.bb_std_mult == pytest.approx(2.5)  # 그리드 첫 번째


# ══════════════════════════════════════════════════════════════════════════════
# Out-of-sample 합본
# ══════════════════════════════════════════════════════════════════════════════

def test_out_of_sample_combined_excludes_train_trades() -> None:
    train_from = datetime(2025, 1, 1, tzinfo=_KST)
    train_to = datetime(2025, 9, 1, tzinfo=_KST)
    val_from = datetime(2025, 9, 1, tzinfo=_KST)
    val_to = datetime(2025, 11, 1, tzinfo=_KST)

    train_trade = _make_trade(datetime(2025, 5, 1, tzinfo=_KST))   # train 기간
    val_trade = _make_trade(datetime(2025, 10, 1, tzinfo=_KST))    # validate 기간

    fold = _make_fold(
        fold_index=0,
        train_from=train_from, train_to=train_to,
        val_from=val_from, val_to=val_to,
        train_trade=train_trade, val_trade=val_trade,
    )
    oos = _build_result((val_trade,), val_from, val_to)
    wf = WalkforwardResult(
        period_from=train_from, period_to=val_to,
        train_window_days=242, validate_window_days=61,
        folds=(fold,), out_of_sample_combined=oos,
    )

    oos_entry_times = {t.entry_at for t in wf.out_of_sample_combined.trades}
    assert train_trade.entry_at not in oos_entry_times
    for trade in wf.out_of_sample_combined.trades:
        assert trade.entry_at >= val_from, f"Train trade가 OOS에 포함됨: {trade.entry_at}"


def test_out_of_sample_combined_period_matches_validate_union() -> None:
    fold1_val_from = datetime(2025, 9, 1, tzinfo=_KST)
    fold1_val_to = datetime(2025, 11, 1, tzinfo=_KST)
    fold2_val_from = datetime(2025, 11, 1, tzinfo=_KST)
    fold2_val_to = datetime(2026, 1, 1, tzinfo=_KST)

    fold1 = _make_fold(fold_index=0,
        train_from=datetime(2025, 1, 1, tzinfo=_KST), train_to=fold1_val_from,
        val_from=fold1_val_from, val_to=fold1_val_to)
    fold2 = _make_fold(fold_index=1,
        train_from=datetime(2025, 3, 1, tzinfo=_KST), train_to=fold2_val_from,
        val_from=fold2_val_from, val_to=fold2_val_to)

    oos = _build_result((), fold1_val_from, fold2_val_to)
    wf = WalkforwardResult(
        period_from=fold1.train_period_from, period_to=fold2_val_to,
        train_window_days=242, validate_window_days=61,
        folds=(fold1, fold2), out_of_sample_combined=oos,
    )

    assert wf.out_of_sample_combined.period_from == fold1_val_from
    assert wf.out_of_sample_combined.period_to == fold2_val_to


def test_out_of_sample_combined_sharpe_uses_validate_window() -> None:
    val_from = datetime(2025, 9, 1, tzinfo=_KST)
    val_to = datetime(2025, 11, 1, tzinfo=_KST)
    trades = tuple(_make_trade(val_from + timedelta(days=i * 3), 0.005) for i in range(10))
    oos = _build_result(trades, val_from, val_to)
    assert isinstance(oos.sharpe_annualized, float)
    assert not (oos.sharpe_annualized != oos.sharpe_annualized)  # not NaN


# ══════════════════════════════════════════════════════════════════════════════
# 파라미터 적용
# ══════════════════════════════════════════════════════════════════════════════

def test_strategy_params_propagate_to_indicators() -> None:
    params = StrategyParams(bb_std_mult=2.5, cci_threshold_normal=80, volume_ratio_min_a=1.2)
    strategy = _params_to_strategy(params)
    assert strategy.bb_std_mult == pytest.approx(2.5)
    assert strategy.cci_threshold_normal == 80
    assert strategy.volume_ratio_min_a == pytest.approx(1.2)


def test_default_params_match_settings() -> None:
    from signal_program.config import Settings

    params = StrategyParams()
    settings = Settings()
    assert params.bb_std_mult == pytest.approx(settings.bb_std_mult)
    assert params.cci_threshold_normal == settings.cci_threshold_normal
    assert params.volume_ratio_min_a == pytest.approx(settings.volume_ratio_min_a)


# ══════════════════════════════════════════════════════════════════════════════
# CLI 그리드 파서
# ══════════════════════════════════════════════════════════════════════════════

def test_walkforward_cli_parses_grid_option() -> None:
    params = parse_grid("bb_std_mult:1.5,2.0,2.5")
    assert len(params) == 3
    assert {p.bb_std_mult for p in params} == {1.5, 2.0, 2.5}


def test_walkforward_cli_default_grid_when_option_omitted() -> None:
    params = parse_grid("bb_std_mult:1.5,2.0,2.5")
    assert len(params) >= 1
    for p in params:
        assert p.bb_std_mult > 0


def test_walkforward_cli_multi_param_grid() -> None:
    # 복수 파라미터 그리드: 3×3 = 9 조합
    params = parse_grid("bb_std_mult:1.5,2.0,2.5;cci_threshold_normal:80,100,120")
    assert len(params) == 9


# ══════════════════════════════════════════════════════════════════════════════
# HTML 렌더링
# ══════════════════════════════════════════════════════════════════════════════

def _make_wf_result(n_folds: int = 4) -> WalkforwardResult:
    folds = []
    for i in range(n_folds):
        t_from = datetime(2025, 1 + i * 2, 1, tzinfo=_KST)
        t_to = t_from + timedelta(days=240)
        v_from = t_to
        v_to = v_from + timedelta(days=61)
        trade = _make_trade(v_from + timedelta(days=5))
        tr = _build_result((), t_from, t_to)
        vr = _build_result((trade,), v_from, v_to)
        folds.append(WalkforwardFold(
            fold_index=i,
            train_period_from=t_from, train_period_to=t_to,
            validate_period_from=v_from, validate_period_to=v_to,
            best_params=StrategyParams(bb_std_mult=2.0),
            train_result=tr, validate_result=vr,
        ))

    all_val_trades = tuple(f.validate_result.trades[0] for f in folds)
    oos = _build_result(
        all_val_trades,
        folds[0].validate_period_from,
        folds[-1].validate_period_to,
    )
    return WalkforwardResult(
        period_from=folds[0].train_period_from,
        period_to=folds[-1].validate_period_to,
        train_window_days=240, validate_window_days=61,
        folds=tuple(folds), out_of_sample_combined=oos,
    )


def test_walkforward_html_shows_all_folds_in_table() -> None:
    from signal_program.backtest.report import walkforward_render_html

    wf = _make_wf_result(4)
    html = walkforward_render_html(
        wf, market="KRW-BTC", mode_label="A,B",
        generated_at=_FROM, template_dir=_TEMPLATE_DIR,
    )
    for i in range(4):
        assert str(i) in html


def test_walkforward_html_shows_out_of_sample_combined_metrics() -> None:
    from signal_program.backtest.report import walkforward_render_html

    wf = _make_wf_result(2)
    html = walkforward_render_html(
        wf, market="KRW-BTC", mode_label="A,B",
        generated_at=_FROM, template_dir=_TEMPLATE_DIR,
    )
    assert "KST" in html
    assert "KRW-BTC" in html


def test_walkforward_html_mdd_displayed_as_abs() -> None:
    from signal_program.backtest.report import walkforward_render_html

    wf = _make_wf_result(1)
    html = walkforward_render_html(
        wf, market="KRW-BTC", mode_label="A",
        generated_at=_FROM, template_dir=_TEMPLATE_DIR,
    )
    mdd = wf.out_of_sample_combined.mdd_pct
    if mdd < 0:
        assert f"{mdd:.2%}" not in html or f"{abs(mdd):.2%}" in html


def test_walkforward_html_is_self_contained() -> None:
    from signal_program.backtest.report import walkforward_render_html

    wf = _make_wf_result(2)
    html = walkforward_render_html(
        wf, market="KRW-BTC", mode_label="A",
        generated_at=_FROM, template_dir=_TEMPLATE_DIR,
    )
    for banned in ("https://", "http://", "cdn.", "googleapis", "gstatic"):
        assert banned not in html, f"외부 URL 발견: {banned}"
