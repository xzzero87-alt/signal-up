"""signal_feedback 저장소 단위 테스트 (ADR-0010 R_P1_10).

핸드오프 §6.2 기반.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import signal_program.state.signal_feedback as fb_module
from signal_program.state.signal_feedback import (
    build_signal_id,
    load_feedback_map,
    save_feedback,
)


@pytest.fixture(autouse=True)
def _use_tmp_feedback_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_FEEDBACK_FILE 을 tmp_path 아래로 교체."""
    monkeypatch.setattr(fb_module, "_FEEDBACK_FILE", tmp_path / "state" / "signal_feedback.jsonl")


# ── 정상 동작 ─────────────────────────────────────────────────────────────────


def test_save_and_load_feedback() -> None:
    """두 개의 피드백을 저장하면 load_feedback_map 이 정확히 반환한다."""
    save_feedback("id1", "KRW-BTC", "helpful")
    save_feedback("id2", "KRW-ETH", "bad")

    fm = load_feedback_map()
    assert fm["id1"] == "helpful"
    assert fm["id2"] == "bad"


def test_latest_wins() -> None:
    """같은 signal_id 에 두 번 피드백 → 최신 값이 우선한다."""
    save_feedback("id1", "KRW-BTC", "helpful")
    save_feedback("id1", "KRW-BTC", "bad")

    fm = load_feedback_map()
    assert fm["id1"] == "bad"


def test_load_feedback_map_empty_if_no_file() -> None:
    """파일이 없으면 빈 dict 반환."""
    result = load_feedback_map()
    assert result == {}


def test_build_signal_id() -> None:
    """signal_id 형식 검증 및 market 역추출 가능성 확인."""
    sid = build_signal_id("2026-01-01T09:00:00+09:00", "KRW-BTC")
    assert sid == "2026-01-01T09:00:00+09:00_KRW-BTC"
    # rsplit("_", 1) 로 market 복원 가능
    parts = sid.rsplit("_", 1)
    assert parts[-1] == "KRW-BTC"


def test_load_skips_legacy_records(tmp_path: Path) -> None:
    """signal_id 없는 기존 포맷 레코드(레거시 피드백)는 skip 한다."""
    legacy = {
        "recorded_at": "2026-01-01T00:00:00+09:00",
        "market": "KRW-BTC",
        "triggered_at": "2026-01-01T09:00:00+09:00",
        "label": "👍",
    }
    fb_module._FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with fb_module._FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(legacy) + "\n")

    fm = load_feedback_map()
    assert fm == {}
