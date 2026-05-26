"""GET /api/signals/stats — 거짓신호율 집계 엔드포인트 단위 테스트 (R_P1_14).

핸드오프 §5.2 기반. test_feedback_api.py 와 동일한 TestClient 패턴 사용.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import signal_program.state.signal_feedback as fb_module
from signal_program.state.signal_feedback import save_feedback
from signal_program.web.api.signals import router


@pytest.fixture()
def stats_fb_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """_FEEDBACK_FILE 을 tmp_path 로 교체한다."""
    path = tmp_path / "state" / "signal_feedback.jsonl"
    monkeypatch.setattr(fb_module, "_FEEDBACK_FILE", path)
    return path


@pytest.fixture()
def client(stats_fb_file: Path) -> TestClient:  # noqa: ARG001 — side effect only
    """signals 라우터만 포함한 최소 TestClient."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── 정상 동작 ─────────────────────────────────────────────────────────────────


def test_stats_no_data(client: TestClient) -> None:
    """피드백 없으면 has_data=False, bad_rate=0.0, window=30."""
    resp = client.get("/api/signals/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is False
    assert data["bad_rate"] == 0.0
    assert data["window"] == 30
    assert data["total_count"] == 0


def test_stats_with_data(client: TestClient, stats_fb_file: Path) -> None:  # noqa: ARG001
    """피드백 5건(bad 2) → bad_rate=40.0, has_data=True."""
    save_feedback("id1", "KRW-BTC", "bad")
    save_feedback("id2", "KRW-ETH", "helpful")
    save_feedback("id3", "KRW-XRP", "bad")
    save_feedback("id4", "KRW-SOL", "helpful")
    save_feedback("id5", "KRW-ADA", "helpful")

    resp = client.get("/api/signals/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is True
    assert data["bad_count"] == 2
    assert data["total_count"] == 5
    assert data["bad_rate"] == 40.0


def test_stats_custom_window(client: TestClient) -> None:
    """window=5 쿼리 파라미터가 응답에 반영된다."""
    resp = client.get("/api/signals/stats?window=5")

    assert resp.status_code == 200
    assert resp.json()["window"] == 5


def test_stats_window_too_small(client: TestClient) -> None:
    """window=0이면 422 Unprocessable Entity."""
    resp = client.get("/api/signals/stats?window=0")
    assert resp.status_code == 422


def test_stats_window_too_large(client: TestClient) -> None:
    """window=201이면 422 Unprocessable Entity."""
    resp = client.get("/api/signals/stats?window=201")
    assert resp.status_code == 422
