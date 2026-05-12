"""CooldownStore — TDD RED → GREEN 시나리오 12종 + Hypothesis property."""
from __future__ import annotations

import json
import os
import platform
import stat
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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


# ─── Phase 3: Hypothesis property 테스트 ─────────────────────────────────────

_MARKETS = st.sampled_from(["KRW-BTC", "KRW-ETH", "KRW-XRP"])
_MODES = st.sampled_from(list(StrategyMode))
_DIRS = st.sampled_from(list(SignalDirection))
_KEYS = st.builds(CooldownKey, market=_MARKETS, mode=_MODES, direction=_DIRS)


@given(
    offset_secs=st.integers(min_value=0, max_value=7 * 24 * 3600),
    cd_secs=st.integers(min_value=60, max_value=7 * 24 * 3600),
)
@settings(max_examples=100, deadline=2000)
def test_property_mark_then_check_consistent(offset_secs: int, cd_secs: int) -> None:
    """mark_sent 후 is_cooled_down 일관성: offset < cd → True, offset >= cd → False."""
    with tempfile.TemporaryDirectory() as d:
        cd = timedelta(seconds=cd_secs)
        store = CooldownStore(path=Path(d) / "prop.json", cooldown=cd)
        store.mark_sent(KEY, BASE_DT)
        check_time = BASE_DT + timedelta(seconds=offset_secs)
        expected = offset_secs < cd_secs
        assert store.is_cooled_down(KEY, check_time) is expected


@given(cd_secs=st.integers(min_value=60, max_value=7 * 24 * 3600))
@settings(max_examples=50, deadline=2000)
def test_property_arbitrary_cooldown_no_exception(cd_secs: int) -> None:
    """임의 cooldown 값 → 예외 없이 동작."""
    with tempfile.TemporaryDirectory() as d:
        cd = timedelta(seconds=cd_secs)
        store = CooldownStore(path=Path(d) / "arb.json", cooldown=cd)
        store.mark_sent(KEY, BASE_DT)
        result = store.is_cooled_down(KEY, BASE_DT + timedelta(seconds=cd_secs // 2))
        assert isinstance(result, bool)


@given(keys=st.lists(_KEYS, min_size=1, max_size=20, unique=True))
@settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.too_slow])
def test_property_multiple_keys_independent(keys: list[CooldownKey]) -> None:
    """N개 키 mark_sent → 각 키 독립 상태 유지, reload 후에도 동일."""
    with tempfile.TemporaryDirectory() as d:
        store = CooldownStore(path=Path(d) / "multi.json", cooldown=COOLDOWN)
        for key in keys:
            store.mark_sent(key, BASE_DT)
        for key in keys:
            assert store.is_cooled_down(key, BASE_DT) is True
        store.reload()
        for key in keys:
            assert store.is_cooled_down(key, BASE_DT) is True


# ─── Phase 3: 동시성 테스트 ──────────────────────────────────────────────────

def test_concurrent_mark_sent_no_loss(tmp_path: Path) -> None:
    """10개 서로 다른 키 동시 mark_sent → 모두 디스크 영속 (데이터 손실 없음)."""
    path = tmp_path / "concurrent.json"
    store = CooldownStore(path=path, cooldown=COOLDOWN)
    markets = [f"KRW-COIN{i:02d}" for i in range(10)]
    keys = [
        CooldownKey(market=m, mode=StrategyMode.MEAN_REVERSION, direction=SignalDirection.BUY)
        for m in markets
    ]
    errors: list[Exception] = []

    def worker(k: CooldownKey) -> None:
        try:
            store.mark_sent(k, BASE_DT)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(k,)) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # 새 인스턴스로 디스크 검증
    store2 = CooldownStore(path=path, cooldown=COOLDOWN)
    for k in keys:
        assert store2.is_cooled_down(k, BASE_DT) is True


def test_reload_matches_disk(tmp_path: Path) -> None:
    """reload() 후 메모리 == 디스크 일치."""
    path = tmp_path / "reload.json"
    store1 = CooldownStore(path=path, cooldown=COOLDOWN)
    store1.mark_sent(KEY, BASE_DT)

    store2 = CooldownStore(path=path, cooldown=COOLDOWN)
    later = BASE_DT + timedelta(hours=1)
    key2 = CooldownKey("KRW-ETH", StrategyMode.SQUEEZE_BREAKOUT, SignalDirection.SELL)
    store2.mark_sent(key2, later)

    store1.reload()
    assert store1.is_cooled_down(KEY, BASE_DT) is True
    assert store1.is_cooled_down(key2, later) is True


# ─── Phase 3: 파일 권한 (Unix only) ─────────────────────────────────────────

@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Unix only — Windows ACL은 chmod 600 미지원 (ADR-0009: Windows는 직접 쓰기로 우회)",
)
def test_file_permissions_600(tmp_path: Path) -> None:
    """mark_sent 후 cooldown.json 권한이 600이어야 한다."""
    path = tmp_path / "perm.json"
    store = CooldownStore(path=path, cooldown=COOLDOWN)
    store.mark_sent(KEY, BASE_DT)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert oct(mode) == "0o600"
