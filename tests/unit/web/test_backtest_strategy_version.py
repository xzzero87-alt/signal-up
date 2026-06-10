"""BacktestJobSubmit strategy_version 필드 + 잡 실행기 전략 선택 단위 테스트 (v2.4)."""

from __future__ import annotations

from datetime import UTC, date

import pytest

from signal_program.web.schemas import BacktestJobSubmit

# ── BacktestJobSubmit 스키마 ──────────────────────────────────────────────────


def test_submit_defaults_to_v1() -> None:
    s = BacktestJobSubmit(
        market="KRW-BTC",
        period_from=date(2025, 1, 1),
        period_to=date(2025, 2, 1),
    )
    assert s.strategy_version == "v1"


@pytest.mark.parametrize("ver", ["v1", "v2", "v3", "v4", "v5"])
def test_submit_accepts_all_versions(ver: str) -> None:
    s = BacktestJobSubmit(
        market="KRW-BTC",
        period_from=date(2025, 1, 1),
        period_to=date(2025, 2, 1),
        strategy_version=ver,
    )
    assert s.strategy_version == ver


def test_submit_rejects_unknown_version() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BacktestJobSubmit(
            market="KRW-BTC",
            period_from=date(2025, 1, 1),
            period_to=date(2025, 2, 1),
            strategy_version="v9",  # type: ignore[arg-type]
        )


def test_submit_v1_backward_compat_no_strategy_version_key() -> None:
    s = BacktestJobSubmit.model_validate(
        {"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"}
    )
    assert s.strategy_version == "v1"


# ── JobSpec strategy_version 전파 ─────────────────────────────────────────────


def test_job_spec_default_strategy_version() -> None:
    from datetime import datetime

    from signal_program.web.jobs import JobKind, JobSpec

    spec = JobSpec(
        kind=JobKind.BACKTEST,
        market="KRW-BTC",
        period_from=datetime(2025, 1, 1, tzinfo=UTC),
        period_to=datetime(2025, 2, 1, tzinfo=UTC),
        mode="both",
    )
    assert spec.strategy_version == "v1"


@pytest.mark.parametrize("ver", ["v1", "v2", "v3", "v4", "v5"])
def test_job_spec_carries_strategy_version(ver: str) -> None:
    from datetime import datetime

    from signal_program.web.jobs import JobKind, JobSpec

    spec = JobSpec(
        kind=JobKind.BACKTEST,
        market="KRW-BTC",
        period_from=datetime(2025, 1, 1, tzinfo=UTC),
        period_to=datetime(2025, 2, 1, tzinfo=UTC),
        mode="both",
        strategy_version=ver,
    )
    assert spec.strategy_version == ver


# ── get_strategy 팩토리 호출 검증 ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ver", "expected_cls"),
    [
        ("v1", "BbCciStrategy"),
        ("v2", "FourIndicatorStrategy"),
        ("v3", "FractalStrategy"),
        ("v4", "DonchianStrategy"),
        ("v5", "Rsi2Strategy"),
    ],
)
def test_get_strategy_returns_correct_class(ver: str, expected_cls: str) -> None:
    from signal_program.config import Settings
    from signal_program.strategies import get_strategy

    strategy = get_strategy(ver, Settings())
    assert type(strategy).__name__ == expected_cls
