"""candles_io parquet 라운드트립 테스트 — Phase 1: RED."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from signal_program.backtest.candles_io import load_candles, save_candles
from signal_program.models import Candle

_KST = ZoneInfo("Asia/Seoul")


def _make_candle_kst(i: int, *, market: str = "KRW-BTC") -> Candle:
    from datetime import timedelta

    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=_KST)
    return Candle(
        market=market,
        opened_at=base + timedelta(hours=i),
        open=50_000_000.0 + i * 10_000.0,
        high=50_002_000.0 + i * 10_000.0,
        low=49_998_000.0 + i * 10_000.0,
        close=50_001_000.0 + i * 10_000.0,
        volume=10.0,
        quote_volume=500_010_000.0,
    )


# ── 200봉 라운드트립 ──────────────────────────────────────────────────────────

def test_round_trip_200_candles(tmp_path: pytest.TempPathFactory) -> None:
    candles = [_make_candle_kst(i) for i in range(200)]
    path = tmp_path / "test.parquet"  # type: ignore[operator]

    save_candles(candles, path)
    loaded = load_candles(path)

    assert len(loaded) == 200
    for orig, lc in zip(candles, loaded, strict=True):
        assert orig.market == lc.market
        assert orig.opened_at.timestamp() == pytest.approx(lc.opened_at.timestamp())
        assert orig.open == pytest.approx(lc.open)
        assert orig.high == pytest.approx(lc.high)
        assert orig.low == pytest.approx(lc.low)
        assert orig.close == pytest.approx(lc.close)
        assert orig.volume == pytest.approx(lc.volume)
        assert orig.quote_volume == pytest.approx(lc.quote_volume)


# ── KST timezone 보존 ────────────────────────────────────────────────────────

def test_kst_timezone_preserved(tmp_path: pytest.TempPathFactory) -> None:
    candle = _make_candle_kst(0)
    path = tmp_path / "kst.parquet"  # type: ignore[operator]

    save_candles([candle], path)
    loaded = load_candles(path)

    assert len(loaded) == 1
    loaded_dt = loaded[0].opened_at
    assert loaded_dt.tzinfo is not None
    offset = loaded_dt.utcoffset()
    assert offset is not None
    assert int(offset.total_seconds()) == 9 * 3600


# ── 빈 리스트 라운드트립 ──────────────────────────────────────────────────────

def test_round_trip_empty(tmp_path: pytest.TempPathFactory) -> None:
    path = tmp_path / "empty.parquet"  # type: ignore[operator]
    save_candles([], path)
    loaded = load_candles(path)
    assert loaded == []


# ── 잘못된 경로 → FileNotFoundError ──────────────────────────────────────────

def test_load_nonexistent_raises(tmp_path: pytest.TempPathFactory) -> None:
    with pytest.raises(FileNotFoundError):
        load_candles(tmp_path / "nonexistent.parquet")  # type: ignore[arg-type]
