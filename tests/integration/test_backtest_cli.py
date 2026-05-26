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


# ── R_P2_D7: --grid 옵션 ────────────────────────────────────────────────────


def test_backtest_cli_accepts_grid_option() -> None:
    """--grid 옵션이 인식되어야 한다 ('No such option' 오류 없이 종료)."""
    result = runner.invoke(
        app,
        [
            "backtest",
            "--market", "KRW-BTC",
            "--from", "2020-01-01",
            "--to", "2020-01-31",
            "--strategy", "v2",
            "--grid", "obv_weight:0.3,0.4,0.5;buy_threshold:0.60,0.65,0.70",
        ],
    )
    assert "No such option: --grid" not in (result.output or ""), result.output
    assert result.exit_code in (0, 1)  # 캔들 없음(0) 또는 설정 오류(1)


@_NEEDS_DATA
def test_backtest_cli_grid_saves_json() -> None:
    """--grid 옵션으로 실행 시 state/backtest/ 에 JSON 파일이 생성되어야 한다."""
    result = runner.invoke(
        app,
        [
            "backtest",
            "--market", "KRW-BTC",
            "--from", "2025-01-01",
            "--to", "2025-01-31",
            "--strategy", "v2",
            "--grid", "obv_weight:0.3,0.4;buy_threshold:0.60,0.65",
        ],
    )
    assert result.exit_code == 0, result.output
    json_files = list(Path("state/backtest").glob("v2_grid_*.json"))
    assert len(json_files) > 0, "JSON 파일이 생성되어야 함"


# ── walkforward V2 fold 테이블 컬럼 버그 픽스 검증 ─────────────────────────

_CANDLE_PATH_2025_10 = Path("data/candles/KRW-BTC/60/2025-10.parquet")
_NEEDS_10M_DATA = pytest.mark.skipif(
    not (_CANDLE_PATH.exists() and _CANDLE_PATH_2025_10.exists()),
    reason="Candle data (2025-01 ~ 2025-10) not available",
)


@_NEEDS_10M_DATA
def test_walkforward_v2_fold_table_shows_grid_param_column() -> None:
    """V2 그리드 walkforward: fold 테이블에 실제 그리드 파라미터 컬럼이 나와야 한다."""
    result = runner.invoke(
        app,
        [
            "walkforward",
            "--market", "KRW-BTC",
            "--from", "2025-01-01",
            "--to", "2025-10-31",
            "--train-months", "6",
            "--validate-months", "2",
            "--strategy", "v2",
            "--grid", "buy_threshold:0.30,0.40",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "buy_threshold" in result.output, "V2 그리드 키가 컬럼 헤더에 나와야 함"
    assert "최적 bb_std" not in result.output, "V1 전용 bb_std 컬럼이 V2에서 노출되면 안 됨"


@_NEEDS_10M_DATA
def test_walkforward_v1_fold_table_shows_bb_std_mult_column() -> None:
    """V1 그리드 walkforward: fold 테이블에 'bb_std_mult' 컬럼이 유지되어야 한다."""
    result = runner.invoke(
        app,
        [
            "walkforward",
            "--market", "KRW-BTC",
            "--from", "2025-01-01",
            "--to", "2025-10-31",
            "--train-months", "6",
            "--validate-months", "2",
            "--grid", "bb_std_mult:1.5,2.0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "bb_std_mult" in result.output, "V1 그리드 키가 컬럼 헤더에 나와야 함"


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
