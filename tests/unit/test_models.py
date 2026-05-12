from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from signal_program.enums import (
    SignalDirection,
    SignalStrength,
    StrategyMode,
    Timeframe,
)
from signal_program.models import Candle, IndicatorSnapshot, Signal

_NOW = dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=dt.UTC)


@pytest.fixture
def valid_candle() -> Candle:
    return Candle(
        market="KRW-BTC",
        opened_at=_NOW,
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=100.0,
        quote_volume=5050000.0,
    )


@pytest.fixture
def valid_snapshot() -> IndicatorSnapshot:
    return IndicatorSnapshot(
        bb_upper=55000.0,
        bb_middle=50000.0,
        bb_lower=45000.0,
        bb_width=0.2,
        bb_pct_b=0.6,
        cci=120.0,
        volume_ratio=1.5,
    )


@pytest.fixture
def valid_signal(valid_snapshot: IndicatorSnapshot) -> Signal:
    return Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=50500.0,
        triggered_at=_NOW,
        indicators=valid_snapshot,
    )


class TestCandleFrozen:
    def test_cannot_set_attribute(self, valid_candle: Candle) -> None:
        with pytest.raises(ValidationError):
            valid_candle.close = 999.0  # type: ignore[misc]

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Candle(
                market="KRW-BTC",
                opened_at=_NOW,
                open=50000.0,
                high=51000.0,
                low=49000.0,
                close=50500.0,
                volume=100.0,
                quote_volume=5050000.0,
                unexpected=1.0,  # type: ignore[call-arg]
            )

    def test_valid_construction(self, valid_candle: Candle) -> None:
        assert valid_candle.market == "KRW-BTC"
        assert valid_candle.close == pytest.approx(50500.0)


class TestIndicatorSnapshotFrozen:
    def test_cannot_set_attribute(self, valid_snapshot: IndicatorSnapshot) -> None:
        with pytest.raises(ValidationError):
            valid_snapshot.cci = 0.0  # type: ignore[misc]

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            IndicatorSnapshot(
                bb_upper=55000.0,
                bb_middle=50000.0,
                bb_lower=45000.0,
                bb_width=0.2,
                bb_pct_b=0.6,
                cci=120.0,
                volume_ratio=1.5,
                unexpected=999.0,  # type: ignore[call-arg]
            )

    def test_volume_ratio_non_negative_constraint(self) -> None:
        with pytest.raises(ValidationError):
            IndicatorSnapshot(
                bb_upper=55000.0,
                bb_middle=50000.0,
                bb_lower=45000.0,
                bb_width=0.2,
                bb_pct_b=0.6,
                cci=120.0,
                volume_ratio=-0.1,
            )

    def test_bb_width_quantile_defaults_none(self, valid_snapshot: IndicatorSnapshot) -> None:
        assert valid_snapshot.bb_width_quantile is None

    def test_bb_width_quantile_accepts_value(self) -> None:
        snap = IndicatorSnapshot(
            bb_upper=55000.0,
            bb_middle=50000.0,
            bb_lower=45000.0,
            bb_width=0.2,
            bb_pct_b=0.6,
            cci=120.0,
            volume_ratio=1.5,
            bb_width_quantile=0.75,
        )
        assert snap.bb_width_quantile == pytest.approx(0.75)


class TestSignalFrozen:
    def test_cannot_set_attribute(self, valid_signal: Signal) -> None:
        with pytest.raises(ValidationError):
            valid_signal.price = 0.0  # type: ignore[misc]

    def test_extra_field_forbidden(self, valid_snapshot: IndicatorSnapshot) -> None:
        with pytest.raises(ValidationError):
            Signal(
                market="KRW-BTC",
                timeframe=Timeframe.HOUR_1,
                mode=StrategyMode.MEAN_REVERSION,
                direction=SignalDirection.BUY,
                strength=SignalStrength.NORMAL,
                price=50500.0,
                triggered_at=_NOW,
                indicators=valid_snapshot,
                extra=True,  # type: ignore[call-arg]
            )

    def test_indicators_type(self, valid_signal: Signal) -> None:
        assert isinstance(valid_signal.indicators, IndicatorSnapshot)

    def test_enums_roundtrip(self, valid_signal: Signal) -> None:
        assert valid_signal.timeframe == Timeframe.HOUR_1
        assert valid_signal.mode == StrategyMode.MEAN_REVERSION
        assert valid_signal.direction == SignalDirection.BUY
        assert valid_signal.strength == SignalStrength.NORMAL
