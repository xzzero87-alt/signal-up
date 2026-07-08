"""Strategy 카탈로그 — ADR-0010 §4 Module-level Registry.

STRATEGY_CATALOG: v1 / v2 팩토리 매핑
get_strategy(version, settings): 전략 인스턴스 반환
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from signal_program.strategies.bb_cci import BbCciStrategy
from signal_program.strategies.donchian import DonchianStrategy
from signal_program.strategies.fractal import FractalStrategy
from signal_program.strategies.kr_fractal import KrFractalStrategy
from signal_program.strategies.rsi2 import Rsi2Strategy
from signal_program.strategies.v2_4indicator import FourIndicatorStrategy

if TYPE_CHECKING:
    from collections.abc import Callable

    from signal_program.config import Settings
    from signal_program.strategies.base import Strategy


def _build_v1(settings: Settings) -> BbCciStrategy:
    """Settings → BbCciStrategy (V1 코드 시그니처 불변 유지, adapter)."""
    return BbCciStrategy(
        bb_period=settings.bb_period,
        bb_std_mult=settings.bb_std_mult,
        cci_period=settings.cci_period,
        cci_threshold_normal=settings.cci_threshold_normal,
        cci_threshold_strong=settings.cci_threshold_strong,
        volume_ratio_min_a=settings.volume_ratio_min_a,
        squeeze_lookback=settings.squeeze_lookback,
        squeeze_quantile=settings.squeeze_quantile,
        volume_ratio_min_b=settings.volume_ratio_min_b,
        regime_filter=settings.v1_regime_filter,
        regime_sma_period=settings.v1_regime_sma_period,
    )


def _build_fractal(settings: Settings) -> FractalStrategy:
    """Settings → 암호화폐 FractalStrategy (V3, 설계 v2.3 §3.1)."""
    return FractalStrategy(
        fractal_lookback=settings.fractal_lookback,
        fractal_volume_threshold=settings.fractal_volume_threshold,
        fractal_volume_strong=settings.fractal_volume_strong,
        fractal_max_age=settings.fractal_max_age,
    )


def _build_donchian(settings: Settings) -> DonchianStrategy:
    """Settings → DonchianStrategy (V4, 설계 v2.3 §3.2)."""
    return DonchianStrategy(
        donchian_entry_period=settings.donchian_entry_period,
        donchian_exit_period=settings.donchian_exit_period,
        donchian_volume_strong=settings.donchian_volume_strong,
    )


def _build_rsi2(settings: Settings) -> Rsi2Strategy:
    """Settings → Rsi2Strategy (V5, 설계 v2.3 §3.3)."""
    return Rsi2Strategy(
        rsi2_period=settings.rsi2_period,
        rsi2_oversold=settings.rsi2_oversold,
        rsi2_overbought=settings.rsi2_overbought,
        rsi2_trend_period=settings.rsi2_trend_period,
    )


def _build_kr_fractal(settings: Settings) -> KrFractalStrategy:
    """Settings → KrFractalStrategy (국장 일봉 백테스트용, ADR-0023)."""
    return KrFractalStrategy(
        fractal_lookback=settings.fractal_lookback,
        fractal_volume_threshold=settings.fractal_volume_threshold,
        fractal_volume_strong=settings.fractal_volume_strong,
    )


#: 전략 버전 → 팩토리 매핑 (ADR-0010 §4 / 전략 확장 v2.3)
STRATEGY_CATALOG: dict[str, Callable[[Settings], Strategy]] = {
    "v1": _build_v1,
    "v2": FourIndicatorStrategy,
    "v3": _build_fractal,
    "v4": _build_donchian,
    "v5": _build_rsi2,
    "kr_fractal": _build_kr_fractal,
}


def get_strategy(version: str, settings: Settings) -> Strategy:
    """전략 버전 문자열로 인스턴스를 생성해 반환한다.

    Parameters
    ----------
    version:
        "v1"~"v5".
    settings:
        config.Settings 인스턴스.

    Raises
    ------
    ValueError:
        알 수 없는 버전 문자열.
    """
    if version not in STRATEGY_CATALOG:
        raise ValueError(
            f"전략 버전은 {list(STRATEGY_CATALOG.keys())} 중 하나여야 합니다 (입력: {version!r})"
        )
    return STRATEGY_CATALOG[version](settings)
