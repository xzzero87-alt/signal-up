"""BacktestReportRenderer 단위 테스트 — Phase 1: RED (report.py 미존재 → ImportError)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from signal_program.backtest.metrics import BacktestResult, TradeRecord
from signal_program.backtest.report import BacktestReportRenderer
from signal_program.enums import SignalDirection, StrategyMode

_KST = ZoneInfo("Asia/Seoul")
_BASE = datetime(2025, 1, 1, 0, 0, 0, tzinfo=_KST)
_TEMPLATE_DIR = Path(__file__).parents[3] / "templates"


def _make_result(
    *,
    mdd_pct: float = -0.5435,
    sharpe: float = -2.03,
    n_trades: int = 3,
) -> BacktestResult:
    trades = tuple(
        TradeRecord(
            market="KRW-BTC",
            mode=StrategyMode.MEAN_REVERSION,
            direction=SignalDirection.BUY,
            entry_at=_BASE + timedelta(days=i * 10),
            entry_price=50_000_000.0,
            exit_at=_BASE + timedelta(days=i * 10, hours=12),
            exit_price=50_000_000.0 * (1.0 + (0.01 if i % 2 == 0 else -0.005)),
            bars_held=12,
            pnl_pct=0.01 if i % 2 == 0 else -0.005,
        )
        for i in range(n_trades)
    )
    return BacktestResult(
        period_from=_BASE,
        period_to=_BASE + timedelta(days=365),
        trades=trades,
        win_rate=0.5,
        avg_pnl_pct=-0.0027,
        cumulative_return_pct=-0.5249,
        mdd_pct=mdd_pct,
        sharpe_annualized=sharpe,
        avg_bars_held=12.0,
    )


@pytest.fixture
def renderer() -> BacktestReportRenderer:
    return BacktestReportRenderer(template_dir=_TEMPLATE_DIR)


@pytest.fixture
def result() -> BacktestResult:
    return _make_result()


# ── 7개 메트릭 모두 포함 ─────────────────────────────────────────────────────

def test_render_html_contains_all_summary_metrics(
    renderer: BacktestReportRenderer, result: BacktestResult
) -> None:
    html = renderer.render_html(result, market="KRW-BTC", mode_label="A+B", generated_at=_BASE)
    assert "KRW-BTC" in html
    assert "50.0%" in html or "50%" in html  # win_rate
    assert "52.49%" in html                  # cumulative
    assert "2.03" in html                    # sharpe
    assert "12.0" in html                    # avg_bars_held


# ── MDD: 양수(abs)로 표시 ─────────────────────────────────────────────────────

def test_render_html_displays_mdd_as_absolute_value(
    renderer: BacktestReportRenderer,
) -> None:
    result = _make_result(mdd_pct=-0.5435)
    html = renderer.render_html(result, market="KRW-BTC", mode_label="A", generated_at=_BASE)
    assert "54.35%" in html
    assert "-54.35%" not in html


# ── Sharpe: 부호 유지 ────────────────────────────────────────────────────────

def test_render_html_displays_sharpe_with_sign(
    renderer: BacktestReportRenderer,
) -> None:
    result = _make_result(sharpe=-2.03)
    html = renderer.render_html(result, market="KRW-BTC", mode_label="A", generated_at=_BASE)
    assert "-2.03" in html


# ── Equity curve base64 PNG 내장 ────────────────────────────────────────────

def test_render_html_embeds_equity_curve_as_base64_png(
    renderer: BacktestReportRenderer, result: BacktestResult
) -> None:
    html = renderer.render_html(result, market="KRW-BTC", mode_label="A", generated_at=_BASE)
    assert 'src="data:image/png;base64,' in html


# ── Drawdown base64 PNG 내장 (이미지 2개 이상) ─────────────────────────────

def test_render_html_embeds_drawdown_as_base64_png(
    renderer: BacktestReportRenderer, result: BacktestResult
) -> None:
    html = renderer.render_html(result, market="KRW-BTC", mode_label="A", generated_at=_BASE)
    assert html.count('src="data:image/png;base64,') >= 2


# ── XSS 방어 (autoescape=True) ──────────────────────────────────────────────

def test_render_html_escapes_market_name(renderer: BacktestReportRenderer) -> None:
    result = _make_result()
    html = renderer.render_html(
        result,
        market="KRW-<script>alert(1)</script>",
        mode_label="A",
        generated_at=_BASE,
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── KST 시각 헤더 표기 ───────────────────────────────────────────────────────

def test_render_html_uses_kst_timezone_in_header(
    renderer: BacktestReportRenderer, result: BacktestResult
) -> None:
    generated = datetime(2025, 6, 1, 14, 30, 0, tzinfo=_KST)
    html = renderer.render_html(result, market="KRW-BTC", mode_label="A", generated_at=generated)
    assert "KST" in html
    assert "2025-06-01" in html


# ── 빈 trades에서도 유효한 HTML (분모 0 안전) ─────────────────────────────────

def test_render_html_with_zero_trades_produces_valid_html(
    renderer: BacktestReportRenderer,
) -> None:
    empty_result = BacktestResult(
        period_from=_BASE,
        period_to=_BASE + timedelta(days=365),
        trades=(),
        win_rate=0.0,
        avg_pnl_pct=0.0,
        cumulative_return_pct=0.0,
        mdd_pct=0.0,
        sharpe_annualized=0.0,
        avg_bars_held=0.0,
    )
    html = renderer.render_html(
        empty_result, market="KRW-BTC", mode_label="A", generated_at=_BASE
    )
    assert "<html" in html.lower()
    assert 'src="data:image/png;base64,' in html


# ── 자기완결 (외부 URL 없음) ─────────────────────────────────────────────────

def test_render_html_is_self_contained(
    renderer: BacktestReportRenderer, result: BacktestResult
) -> None:
    html = renderer.render_html(result, market="KRW-BTC", mode_label="A", generated_at=_BASE)
    for banned in ("https://", "http://", "cdn.", "googleapis", "gstatic"):
        assert banned not in html, f"외부 URL 발견: {banned}"
