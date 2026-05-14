"""backtest CLI 통합 테스트 — --report-html 옵션.

Phase 1 RED: --report-html 미구현 → 옵션 오류 / 파일 미생성
실제 parquet 데이터(data/candles/KRW-BTC/60/2025-01.parquet)를 사용하므로
fetch-candles 실행 후에만 동작. 데이터 없으면 스킵.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from signal_program.cli import app

runner = CliRunner()

_CANDLE_PATH = Path("data/candles/KRW-BTC/60/2025-01.parquet")
_NEEDS_DATA = pytest.mark.skipif(
    not _CANDLE_PATH.exists(),
    reason="Candle data not available — run fetch-candles first",
)


# ── --report-html 지정 시 HTML 파일 생성 ────────────────────────────────────

@_NEEDS_DATA
def test_backtest_cli_writes_html_when_report_option_given(
    tmp_path: pytest.TempPathFactory,
) -> None:
    html_path = tmp_path / "report.html"  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "backtest",
            "--market", "KRW-BTC",
            "--from", "2025-01-01",
            "--to", "2025-01-31",
            "--report-html", str(html_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert html_path.exists(), "HTML 파일이 생성되어야 함"
    html_content = html_path.read_text(encoding="utf-8")
    assert "<html" in html_content.lower()


# ── --report-html 중간 디렉토리 자동 생성 ──────────────────────────────────

@_NEEDS_DATA
def test_backtest_cli_creates_parent_directories(
    tmp_path: pytest.TempPathFactory,
) -> None:
    nested_path = tmp_path / "nested" / "deep" / "report.html"  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "backtest",
            "--market", "KRW-BTC",
            "--from", "2025-01-01",
            "--to", "2025-01-31",
            "--report-html", str(nested_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert nested_path.exists()


# ── --report-html 없으면 HTML 파일 미생성 (기존 동작 불변) ──────────────────

@_NEEDS_DATA
def test_backtest_cli_default_behavior_unchanged(
    tmp_path: pytest.TempPathFactory,
) -> None:
    result = runner.invoke(
        app,
        [
            "backtest",
            "--market", "KRW-BTC",
            "--from", "2025-01-01",
            "--to", "2025-01-31",
        ],
    )
    assert result.exit_code == 0, result.output
    html_files = list(tmp_path.glob("**/*.html"))  # type: ignore[union-attr]
    assert len(html_files) == 0
