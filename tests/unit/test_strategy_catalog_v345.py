"""전략 v3/v4/v5 카탈로그 등록 + config 파라미터 검증 (설계 v2.3 §5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from signal_program.config import Settings
from signal_program.strategies import get_strategy
from signal_program.strategies.donchian import DonchianStrategy
from signal_program.strategies.fractal import FractalStrategy
from signal_program.strategies.rsi2 import Rsi2Strategy


def test_catalog_builds_new_strategies() -> None:
    s = Settings()
    assert isinstance(get_strategy("v3", s), FractalStrategy)
    assert isinstance(get_strategy("v4", s), DonchianStrategy)
    assert isinstance(get_strategy("v5", s), Rsi2Strategy)


def test_settings_accepts_new_versions() -> None:
    for v in ("v1", "v2", "v3", "v4", "v5"):
        assert Settings(strategy_version=v).strategy_version == v


def test_param_defaults() -> None:
    s = Settings()
    assert s.donchian_entry_period == 20
    assert s.donchian_exit_period == 10
    assert s.donchian_volume_strong == 1.5
    assert s.rsi2_period == 2
    assert s.rsi2_oversold == 10.0
    assert s.rsi2_overbought == 90.0
    assert s.rsi2_trend_period == 200
    assert s.fractal_max_age == 20


def test_factory_passes_params() -> None:
    s = Settings(donchian_entry_period=30, rsi2_trend_period=150)
    d = get_strategy("v4", s)
    r = get_strategy("v5", s)
    assert isinstance(d, DonchianStrategy)
    assert d.entry_period == 30
    assert isinstance(r, Rsi2Strategy)
    assert r.trend_period == 150


@pytest.mark.parametrize(
    "field,value",
    [
        ("donchian_entry_period", 1),  # < 2
        ("rsi2_period", 1),  # < 2
        ("rsi2_trend_period", 600),  # > 500
        ("rsi2_oversold", 150.0),  # > 100
    ],
)
def test_range_validation_rejects_out_of_bounds(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})
