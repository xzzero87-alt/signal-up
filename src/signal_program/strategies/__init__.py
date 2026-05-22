"""Strategy 카탈로그 — ADR-0010 §4 Module-level Registry.

STRATEGY_CATALOG: v1 / v2 팩토리 매핑
get_strategy(version, settings): 전략 인스턴스 반환
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from signal_program.strategies.bb_cci import BbCciStrategy
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
    )


#: 전략 버전 → 팩토리 매핑 (ADR-0010 §4)
STRATEGY_CATALOG: dict[str, Callable[[Settings], Strategy]] = {
    "v1": _build_v1,
    "v2": FourIndicatorStrategy,
}


def get_strategy(version: str, settings: Settings) -> Strategy:
    """전략 버전 문자열로 인스턴스를 생성해 반환한다.

    Parameters
    ----------
    version:
        "v1" 또는 "v2".
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
