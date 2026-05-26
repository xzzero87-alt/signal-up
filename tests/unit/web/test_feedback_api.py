"""POST /api/signals/{signal_id}/feedback — 카드 뷰 회고 API 단위 테스트 (R_P1_10).

핸드오프 §6.1 기반.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import signal_program.state.signal_feedback as fb_module
from signal_program.web.api.feedback import router


@pytest.fixture()
def feedback_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """feedback 파일을 tmp_path 로 교체한다."""
    path = tmp_path / "state" / "signal_feedback.jsonl"
    monkeypatch.setattr(fb_module, "_FEEDBACK_FILE", path)
    return path


@pytest.fixture()
def client(feedback_file: Path) -> TestClient:  # noqa: ARG001 — side effect only
    """feedback 라우터만 포함한 최소 TestClient."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


_SIGNAL_ID = "2026-01-01T09:00:00+09:00_KRW-BTC"


# ── 정상 동작 ─────────────────────────────────────────────────────────────────


def test_submit_feedback_helpful(client: TestClient, feedback_file: Path) -> None:
    """feedback=helpful 제출 시 200 OK + ok=True 반환."""
    resp = client.post(f"/api/signals/{_SIGNAL_ID}/feedback", json={"feedback": "helpful"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["feedback"] == "helpful"
    assert body["signal_id"] == _SIGNAL_ID


def test_submit_feedback_bad(client: TestClient, feedback_file: Path) -> None:
    """feedback=bad 제출 시 저장 후 ok=True."""
    resp = client.post(f"/api/signals/{_SIGNAL_ID}/feedback", json={"feedback": "bad"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_submit_feedback_persists_to_jsonl(client: TestClient, feedback_file: Path) -> None:
    """POST 후 JSONL 파일에 실제로 기록됐는지 확인한다."""
    client.post(f"/api/signals/{_SIGNAL_ID}/feedback", json={"feedback": "confusing"})
    assert feedback_file.exists()
    lines = [json.loads(line) for line in feedback_file.read_text(encoding="utf-8").splitlines()]
    assert any(
        r.get("signal_id") == _SIGNAL_ID and r.get("feedback") == "confusing"
        for r in lines
    )


# ── 오류 검증 ─────────────────────────────────────────────────────────────────


def test_submit_feedback_invalid_value(client: TestClient) -> None:
    """정의되지 않은 feedback 값 → 422 반환."""
    resp = client.post(f"/api/signals/{_SIGNAL_ID}/feedback", json={"feedback": "unknown_value"})
    assert resp.status_code == 422


def test_submit_feedback_missing_field(client: TestClient) -> None:
    """feedback 필드 누락 → 422 반환."""
    resp = client.post(f"/api/signals/{_SIGNAL_ID}/feedback", json={})
    assert resp.status_code == 422


def test_submit_feedback_extra_field_rejected(client: TestClient) -> None:
    """extra=forbid — 불필요 필드 포함 시 422 반환."""
    resp = client.post(
        f"/api/signals/{_SIGNAL_ID}/feedback",
        json={"feedback": "helpful", "extra_field": "should_fail"},
    )
    assert resp.status_code == 422
