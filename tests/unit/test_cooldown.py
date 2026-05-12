"""CooldownStore — TDD RED → GREEN 시나리오 12종."""
from __future__ import annotations

import json
import platform
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from signal_program.enums import SignalDirection, StrategyMode
from signal_program.state.cooldown import CooldownKey, CooldownStore

KST = ZoneInfo("Asia/Seoul")
COOLDOWN = timedelta(hours=2)
BASE_DT = datetime(2026, 5, 12, 14, 0, tzinfo=KST)
KEY = CooldownKey(
    market="KRW-BTC",
    mode=StrategyMode.MEAN_REVERSION,
    direction=SignalDirection.BUY,
)


def make_store(tmp_path: Path, cooldown: timedelta = COOLDOWN) -> CooldownStore:
    return CooldownStore(path=tmp_path / "cooldown.json", cooldown=cooldown)


# (a) 첫 호출 → False (쿨다운 기록 없음)
@freeze_time("2026-05-12 14:00:00+09:00")
def test_first_call_not_cooled_down(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.is_cooled_down(KEY, BASE_DT) is False


# (b) mark_sent 직후 → True
@freeze_time("2026-05-12 14:00:00+09:00")
def test_marked_then_immediately_cooled(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_sent(KEY, BASE_DT)
    assert store.is_cooled_down(KEY, BASE_DT) is True


# (c) cooldown 미만(1h59m) → True
@freeze_time("2026-05-12 14:00:00+09:00")
def test_before_cooldown_still_blocked(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_sent(KEY, BASE_DT)
    future = BASE_DT + timedelta(hours=1, minutes=59)
    assert store.is_cooled_down(KEY, future) is True


# (d) cooldown 정확(2h) → False (경계는 통과)
@freeze_time("2026-05-12 14:00:00+09:00")
def test_exactly_at_cooldown_passes(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_sent(KEY, BASE_DT)
    future = BASE_DT + timedelta(hours=2)
    assert store.is_cooled_down(KEY, future) is False


# (e) cooldown 초과(2h+1s) → False
@freeze_time("2026-05-12 14:00:00+09:00")
def test_after_cooldown_passes(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_sent(KEY, BASE_DT)
    future = BASE_DT + timedelta(hours=2, seconds=1)
    assert store.is_cooled_down(KEY, future) is False


# (f) 다른 market → 영향 없음
@freeze_time("2026-05-12 14:00:00+09:00")
def test_different_market_independent(tmp_path: Path) -> None:
    other = CooldownKey("KRW-ETH", StrategyMode.MEAN_REVERSION, SignalDirection.BUY)
    store = make_store(tmp_path)
    store.mark_sent(KEY, BASE_DT)
    assert store.is_cooled_down(other, BASE_DT) is False


# (g) 다른 mode → 영향 없음
@freeze_time("2026-05-12 14:00:00+09:00")
def test_different_mode_independent(tmp_path: Path) -> None:
    other = CooldownKey("KRW-BTC", StrategyMode.SQUEEZE_BREAKOUT, SignalDirection.BUY)
    store = make_store(tmp_path)
    store.mark_sent(KEY, BASE_DT)
    assert store.is_cooled_down(other, BASE_DT) is False


# (h) 다른 direction → 영향 없음
@freeze_time("2026-05-12 14:00:00+09:00")
def test_different_direction_independent(tmp_path: Path) -> None:
    other = CooldownKey("KRW-BTC", StrategyMode.MEAN_REVERSION, SignalDirection.SELL)
    store = make_store(tmp_path)
    store.mark_sent(KEY, BASE_DT)
    assert store.is_cooled_down(other, BASE_DT) is False


# (i) 디스크 영속: 인스턴스 2에서 is_cooled_down → True
@freeze_time("2026-05-12 14:00:00+09:00")
def test_disk_persistence(tmp_path: Path) -> None:
    path = tmp_path / "cooldown.json"
    store1 = CooldownStore(path=path, cooldown=COOLDOWN)
    store1.mark_sent(KEY, BASE_DT)
    store2 = CooldownStore(path=path, cooldown=COOLDOWN)
    assert store2.is_cooled_down(KEY, BASE_DT) is True


# (j) 손상된 JSON → graceful 복구 (예외 없음, 빈 상태)
def test_corrupted_file_graceful(tmp_path: Path) -> None:
    path = tmp_path / "cooldown.json"
    path.write_text("not valid json {{ broken", encoding="utf-8")
    store = CooldownStore(path=path, cooldown=COOLDOWN)
    assert store.is_cooled_down(KEY, BASE_DT) is False


# (k) 빈 파일 → 빈 상태
def test_empty_file_graceful(tmp_path: Path) -> None:
    path = tmp_path / "cooldown.json"
    path.write_text("", encoding="utf-8")
    store = CooldownStore(path=path, cooldown=COOLDOWN)
    assert store.is_cooled_down(KEY, BASE_DT) is False


# (l) cooldown 파라미터화: 각 구간 직전/직후 검증
@pytest.mark.parametrize("cd_hours", [1, 2, 6, 24])
def test_various_cooldown_durations(tmp_path: Path, cd_hours: int) -> None:
    cd = timedelta(hours=cd_hours)
    path = tmp_path / f"cd_{cd_hours}.json"
    store = CooldownStore(path=path, cooldown=cd)
    store.mark_sent(KEY, BASE_DT)
    before = BASE_DT + cd - timedelta(minutes=1)
    after = BASE_DT + cd + timedelta(minutes=1)
    assert store.is_cooled_down(KEY, before) is True
    assert store.is_cooled_down(KEY, after) is False
