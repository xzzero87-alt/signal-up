"""generate_snapshot — PNG 생성 단위 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path  # noqa: TC003
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from signal_program.charting.snapshot import generate_snapshot
from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import IndicatorSnapshot, Signal

KST = ZoneInfo("Asia/Seoul")
_PNG_MAGIC = b"\x89PNG"


def make_candles_df(n: int = 100) -> pd.DataFrame:
    """합성 캔들 DataFrame (n봉)."""
    base = datetime(2026, 5, 12, 0, 0, tzinfo=KST)
    closes = [50_000_000.0 + i * 10_000 for i in range(n)]
    return pd.DataFrame(
        {
            "market": ["KRW-BTC"] * n,
            "opened_at": [base + timedelta(hours=i) for i in range(n)],
            "open": closes,
            "high": [c * 1.005 for c in closes],
            "low": [c * 0.995 for c in closes],
            "close": closes,
            "volume": [1.0] * n,
            "quote_volume": [c * 1.0 for c in closes],
        }
    )


def make_signal(
    direction: SignalDirection = SignalDirection.BUY,
    mode: StrategyMode = StrategyMode.MEAN_REVERSION,
) -> Signal:
    return Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=mode,
        direction=direction,
        strength=SignalStrength.NORMAL,
        price=50_000_000.0,
        triggered_at=datetime(2026, 5, 12, 14, 0, tzinfo=KST),
        indicators=IndicatorSnapshot(
            bb_upper=52_000_000.0,
            bb_middle=50_000_000.0,
            bb_lower=48_000_000.0,
            bb_width=0.04,
            bb_pct_b=0.5,
            cci=-150.0,
            volume_ratio=1.3,
            bb_width_quantile=None,
        ),
    )


def test_generates_png_file(tmp_path: Path) -> None:
    out = generate_snapshot(make_candles_df(100), make_signal(), tmp_path)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.read_bytes()[:4] == _PNG_MAGIC


def test_output_dir_created_if_missing(tmp_path: Path) -> None:
    new_dir = tmp_path / "charts" / "subdir"
    assert not new_dir.exists()
    out = generate_snapshot(make_candles_df(100), make_signal(), new_dir)
    assert new_dir.exists()
    assert out.parent == new_dir


def test_filename_format(tmp_path: Path) -> None:
    out = generate_snapshot(make_candles_df(100), make_signal(), tmp_path)
    assert out.name.startswith("KRW_BTC_")
    assert out.suffix == ".png"
    assert "20260512T1400" in out.name


@pytest.mark.parametrize(
    "direction,mode",
    [
        (SignalDirection.BUY, StrategyMode.MEAN_REVERSION),
        (SignalDirection.SELL, StrategyMode.MEAN_REVERSION),
        (SignalDirection.BUY, StrategyMode.SQUEEZE_BREAKOUT),
        (SignalDirection.SELL, StrategyMode.SQUEEZE_BREAKOUT),
    ],
)
def test_all_direction_mode_combinations(
    tmp_path: Path, direction: SignalDirection, mode: StrategyMode
) -> None:
    sig = make_signal(direction=direction, mode=mode)
    out = generate_snapshot(make_candles_df(100), sig, tmp_path)
    assert out.exists()
    assert out.read_bytes()[:4] == _PNG_MAGIC


def test_insufficient_candles_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="80봉"):
        generate_snapshot(make_candles_df(79), make_signal(), tmp_path)


def test_exactly_80_candles_ok(tmp_path: Path) -> None:
    out = generate_snapshot(make_candles_df(80), make_signal(), tmp_path)
    assert out.exists()
