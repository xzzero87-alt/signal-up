"""SignalHistory 단위 테스트 — M14 시그널 이력 JSONL."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from signal_program.state.signal_history import SignalHistory

_KST = ZoneInfo("Asia/Seoul")


def _make_signal_dict(market: str = "KRW-BTC", direction: str = "buy") -> dict:
    return {
        "market": market,
        "timeframe": "60",
        "mode": "A",
        "direction": direction,
        "strength": "normal",
        "price": 50_000_000.0,
        "triggered_at": datetime(2025, 6, 1, 10, 0, tzinfo=_KST).isoformat(),
        "indicators": {
            "bb_upper": 51_000_000.0,
            "bb_middle": 50_000_000.0,
            "bb_lower": 49_000_000.0,
            "bb_width": 2_000_000.0,
            "bb_pct_b": 0.0,
            "cci": -150.0,
            "volume_ratio": 1.5,
        },
    }


@pytest.fixture
def history(tmp_path: Path) -> SignalHistory:
    return SignalHistory(path=tmp_path / "signal_history.jsonl")


def test_append_creates_jsonl_file(history: SignalHistory) -> None:
    history.append(_make_signal_dict())
    assert history._path.exists()
    lines = history._path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1


def test_read_recent_returns_last_n_lines(history: SignalHistory) -> None:
    for _ in range(10):
        history.append(_make_signal_dict())
    records = history.read_recent(limit=5)
    assert len(records) == 5


def test_read_recent_filters_by_market(history: SignalHistory) -> None:
    history.append(_make_signal_dict(market="KRW-BTC"))
    history.append(_make_signal_dict(market="KRW-ETH"))
    history.append(_make_signal_dict(market="KRW-BTC"))
    btc_records = history.read_recent(limit=50, market="KRW-BTC")
    assert all(r["signal"]["market"] == "KRW-BTC" for r in btc_records)
    assert len(btc_records) == 2


def test_rotates_when_file_exceeds_1mb(history: SignalHistory, tmp_path: Path) -> None:
    big_line = "x" * 1000 + "\n"
    history._path.parent.mkdir(parents=True, exist_ok=True)
    history._path.write_text(big_line * 1100, encoding="utf-8")
    history.append(_make_signal_dict())
    rotated = tmp_path / "signal_history.1.jsonl"
    assert rotated.exists() or history._path.stat().st_size < 1024 * 1024
