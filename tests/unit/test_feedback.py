"""POST /api/feedback — TDD.

G3 측정 인프라 (ADR-0010 R_P1_10):
  - 👍/👎 라벨 JSONL 기록
  - 필드 검증 (label enum, 필수 필드, extra=forbid)
  - JSONL 누적 (여러 번 POST)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from signal_program.web.api.feedback import router


# ── 픽스처 ────────────────────────────────────────────────────────────────────


@pytest.fixture()
def feedback_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """JSONL 경로를 tmp_path로 교체한다."""
    import signal_program.web.api.feedback as fb

    path = tmp_path / "signal_feedback.jsonl"
    monkeypatch.setattr(fb, "_FEEDBACK_FILE", path)
    return path


@pytest.fixture()
def client(feedback_file: Path) -> TestClient:  # noqa: ARG001 — side effect only
    """feedback 라우터만 포함한 최소 TestClient."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


_GOOD_PAYLOAD = {
    "market": "KRW-BTC",
    "triggered_at": "2026-05-21T14:00:00+09:00",
    "label": "👍",
}


# ── 정상 동작 ─────────────────────────────────────────────────────────────────


class TestPostFeedbackSuccess:
    def test_good_label_200(self, client: TestClient) -> None:
        res = client.post("/api/feedback", json=_GOOD_PAYLOAD)
        assert res.status_code == 200
        assert res.json() == {"ok": True}

    def test_bad_label_200(self, client: TestClient) -> None:
        payload = {**_GOOD_PAYLOAD, "market": "KRW-ETH", "label": "👎"}
        res = client.post("/api/feedback", json=payload)
        assert res.status_code == 200
        assert res.json() == {"ok": True}


# ── JSONL 파일 내용 ──────────────────────────────────────────────────────────


class TestFeedbackJSONL:
    def test_file_created_after_post(
        self, client: TestClient, feedback_file: Path
    ) -> None:
        assert not feedback_file.exists()
        client.post("/api/feedback", json=_GOOD_PAYLOAD)
        assert feedback_file.exists()

    def test_required_fields_present(
        self, client: TestClient, feedback_file: Path
    ) -> None:
        client.post("/api/feedback", json=_GOOD_PAYLOAD)
        rec = json.loads(feedback_file.read_text(encoding="utf-8").strip())
        assert "recorded_at" in rec
        assert rec["market"] == "KRW-BTC"
        assert rec["triggered_at"] == "2026-05-21T14:00:00+09:00"
        assert rec["label"] == "👍"

    def test_bad_label_stored(self, client: TestClient, feedback_file: Path) -> None:
        client.post("/api/feedback", json={**_GOOD_PAYLOAD, "label": "👎"})
        rec = json.loads(feedback_file.read_text(encoding="utf-8").strip())
        assert rec["label"] == "👎"

    def test_multiple_posts_append(
        self, client: TestClient, feedback_file: Path
    ) -> None:
        for label in ["👍", "👎", "👍"]:
            client.post("/api/feedback", json={**_GOOD_PAYLOAD, "label": label})
        lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["label"] == "👍"
        assert json.loads(lines[1])["label"] == "👎"
        assert json.loads(lines[2])["label"] == "👍"

    def test_recorded_at_is_tz_aware_iso(
        self, client: TestClient, feedback_file: Path
    ) -> None:
        client.post("/api/feedback", json=_GOOD_PAYLOAD)
        rec = json.loads(feedback_file.read_text(encoding="utf-8").strip())
        dt = datetime.fromisoformat(rec["recorded_at"])
        assert dt.tzinfo is not None


# ── 검증 오류 (422) ──────────────────────────────────────────────────────────


class TestFeedbackValidation:
    def test_invalid_label_422(self, client: TestClient) -> None:
        res = client.post("/api/feedback", json={**_GOOD_PAYLOAD, "label": "😐"})
        assert res.status_code == 422

    def test_missing_market_422(self, client: TestClient) -> None:
        res = client.post(
            "/api/feedback",
            json={"triggered_at": "2026-05-21T14:00:00+09:00", "label": "👍"},
        )
        assert res.status_code == 422

    def test_missing_triggered_at_422(self, client: TestClient) -> None:
        res = client.post(
            "/api/feedback", json={"market": "KRW-BTC", "label": "👍"}
        )
        assert res.status_code == 422

    def test_missing_label_422(self, client: TestClient) -> None:
        res = client.post(
            "/api/feedback",
            json={"market": "KRW-BTC", "triggered_at": "2026-05-21T14:00:00+09:00"},
        )
        assert res.status_code == 422

    def test_extra_field_422(self, client: TestClient) -> None:
        """extra=forbid — 알 수 없는 필드 포함 시 422."""
        res = client.post(
            "/api/feedback",
            json={**_GOOD_PAYLOAD, "unknown": "hack"},
        )
        assert res.status_code == 422

    def test_empty_body_422(self, client: TestClient) -> None:
        res = client.post("/api/feedback", json={})
        assert res.status_code == 422
