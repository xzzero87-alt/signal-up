"""SignalLog — 단위 테스트."""
from __future__ import annotations

import json
import os
import platform
import stat
from datetime import datetime
from pathlib import Path  # noqa: TC003
from zoneinfo import ZoneInfo

import pytest

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import IndicatorSnapshot, Signal
from signal_program.state.signal_log import SignalLog

KST = ZoneInfo("Asia/Seoul")
pytestmark = pytest.mark.anyio

BASE_DT = datetime(2026, 5, 12, 14, 0, tzinfo=KST)


def make_signal(market: str = "KRW-BTC") -> Signal:
    return Signal(
        market=market,
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=50_000_000.0,
        triggered_at=BASE_DT,
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


async def test_sequential_appends_produce_valid_jsonl(tmp_path: Path) -> None:
    """5건 순차 append → 5줄 JSON Lines, 각 줄 파싱 가능."""
    slog = SignalLog(path=tmp_path / "signals.jsonl")
    for i in range(5):
        await slog.append(make_signal(f"KRW-COIN{i}"), "ok", BASE_DT)
    lines = (tmp_path / "signals.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    for line in lines:
        rec = json.loads(line)
        assert "signal" in rec and rec["sent_status"] == "ok" and rec["sent_at"]


async def test_concurrent_appends_no_loss(tmp_path: Path) -> None:
    """10건 동시 append → 손실 없이 모두 누적."""
    import asyncio

    path = tmp_path / "concurrent.jsonl"
    slog = SignalLog(path=path)
    markets = [f"KRW-COIN{i:02d}" for i in range(10)]
    await asyncio.gather(*[slog.append(make_signal(m), "ok", BASE_DT) for m in markets])
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 10
    assert {json.loads(l)["signal"]["market"] for l in lines} == set(markets)


async def test_parent_dir_auto_created(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "nested" / "signals.jsonl"
    slog = SignalLog(path=path)
    await slog.append(make_signal(), "dry_run", BASE_DT)
    assert path.exists()


async def test_cooled_down_status_persisted(tmp_path: Path) -> None:
    slog = SignalLog(path=tmp_path / "cd.jsonl")
    await slog.append(make_signal(), "cooled_down", BASE_DT)
    rec = json.loads((tmp_path / "cd.jsonl").read_text())
    assert rec["sent_status"] == "cooled_down"


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Unix only — Windows chmod 600 미지원 (ADR-0009)",
)
async def test_file_permissions_600(tmp_path: Path) -> None:
    slog = SignalLog(path=tmp_path / "perm.jsonl")
    await slog.append(make_signal(), "ok", BASE_DT)
    assert oct(stat.S_IMODE(os.stat(tmp_path / "perm.jsonl").st_mode)) == "0o600"
