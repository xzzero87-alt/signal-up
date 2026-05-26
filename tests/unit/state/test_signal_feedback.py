"""signal_feedback 저장소 단위 테스트 (ADR-0010 R_P1_10, R_P1_14).

핸드오프 §6.2 기반.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import signal_program.state.signal_feedback as fb_module
from signal_program.state.signal_feedback import (
    build_signal_id,
    compute_feedback_stats,
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


# ── compute_feedback_stats (R_P1_14) ──────────────────────────────────────────


class TestComputeFeedbackStats:
    def test_empty_file_returns_no_data(self) -> None:
        """피드백 파일이 없으면 has_data=False."""
        stats = compute_feedback_stats(window=30)
        assert stats["has_data"] is False
        assert stats["total_count"] == 0
        assert stats["bad_rate"] == 0.0

    def test_fewer_than_3_records_returns_no_data(self) -> None:
        """레코드 2개는 표본 부족 — has_data=False."""
        save_feedback("id1", "KRW-BTC", "bad")
        save_feedback("id2", "KRW-ETH", "helpful")

        stats = compute_feedback_stats(window=30)
        assert stats["has_data"] is False
        assert stats["total_count"] == 2

    def test_bad_rate_calculated_correctly(self) -> None:
        """4건 중 bad 1건 → bad_rate=25.0."""
        save_feedback("id1", "KRW-BTC", "helpful")
        save_feedback("id2", "KRW-ETH", "confusing")
        save_feedback("id3", "KRW-XRP", "bad")
        save_feedback("id4", "KRW-SOL", "helpful")

        stats = compute_feedback_stats(window=30)
        assert stats["has_data"] is True
        assert stats["bad_count"] == 1
        assert stats["total_count"] == 4
        assert stats["bad_rate"] == 25.0

    def test_window_limits_to_last_n_records(self) -> None:
        """window=3이면 마지막 3건만 집계."""
        # 앞 2건 bad, 뒤 3건 helpful
        for i in range(2):
            save_feedback(f"bad{i}", "KRW-BTC", "bad")
        for i in range(3):
            save_feedback(f"ok{i}", "KRW-ETH", "helpful")

        stats = compute_feedback_stats(window=3)
        # 마지막 3건(helpful)만 집계 → bad=0
        assert stats["bad_count"] == 0
        assert stats["total_count"] == 3
        assert stats["bad_rate"] == 0.0

    def test_all_bad_returns_100_percent(self) -> None:
        """전부 bad이면 bad_rate=100.0."""
        for i in range(5):
            save_feedback(f"id{i}", "KRW-BTC", "bad")

        stats = compute_feedback_stats(window=30)
        assert stats["bad_rate"] == 100.0
        assert stats["has_data"] is True
