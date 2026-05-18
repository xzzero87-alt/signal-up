"""M13 FastAPI 백엔드 통합 테스트 — Phase 1: RED.

TestClient로 모든 라우트 200/422 확인. 시크릿 마스킹·보안 가드·settings_store 포함.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from signal_program.web.app import create_app


@pytest.fixture
def tmp_settings_path(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


@pytest.fixture
def client(tmp_settings_path: Path, tmp_path: Path):  # type: ignore[no-untyped-def]
    def _noop(spec: object, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>ok</html>", encoding="utf-8")

    app = create_app(
        settings_path=tmp_settings_path,
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
        _job_executor=_noop,
    )
    with TestClient(app) as c:
        yield c


# ── Health ─────────────────────────────────────────────────────────────────

def test_health_returns_200_with_version(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── Settings GET ───────────────────────────────────────────────────────────

def test_get_settings_returns_200(client: TestClient) -> None:
    resp = client.get("/api/settings")
    assert resp.status_code == 200


def test_get_settings_returns_masked_secrets(client: TestClient) -> None:
    resp = client.get("/api/settings")
    data = resp.json()
    assert "telegram_bot_token_masked" in data
    # 토큰 평문 패턴 없음
    assert not re.search(r"\d{8,}:[A-Za-z0-9_-]{30,}", resp.text)


def test_get_settings_response_never_contains_raw_token(client: TestClient) -> None:
    resp = client.get("/api/settings")
    assert not re.search(r"\d{8,}:[A-Za-z0-9_-]{30,}", resp.text)


# ── Settings PUT ───────────────────────────────────────────────────────────

def test_put_settings_validates_field_constraints(client: TestClient) -> None:
    resp = client.put("/api/settings", json={"bb_period": 0})
    assert resp.status_code == 422


def test_put_settings_returns_korean_validation_messages(client: TestClient) -> None:
    resp = client.put("/api/settings", json={"bb_period": 0})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    messages = [e["message"] for e in detail]
    assert any("이상이어야 합니다" in m for m in messages)


def test_put_settings_response_field_has_no_body_prefix(client: TestClient) -> None:
    """결함 회귀: 422 응답의 field 값에 'body.' prefix가 없어야 한다."""
    resp = client.put("/api/settings", json={"bb_period": 0})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    fields = [e["field"] for e in detail]
    assert any(f == "bb_period" for f in fields), f"field='bb_period' 기대, 실제: {fields}"
    assert not any(f.startswith("body.") for f in fields), f"body. prefix 포함: {fields}"


def test_put_settings_valid_update_returns_200(client: TestClient) -> None:
    resp = client.put("/api/settings", json={"bb_period": 25, "dry_run": True})
    assert resp.status_code == 200


def test_put_settings_persists_to_state_settings_json(
    client: TestClient, tmp_settings_path: Path
) -> None:
    client.put("/api/settings", json={"bb_period": 30})
    assert tmp_settings_path.exists()
    data = json.loads(tmp_settings_path.read_text(encoding="utf-8"))
    assert data.get("bb_period") == 30


# ── Signals ────────────────────────────────────────────────────────────────

def test_signals_recent_returns_list(client: TestClient) -> None:
    resp = client.get("/api/signals/recent")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Backtest ───────────────────────────────────────────────────────────────

def test_backtest_get_jobs_returns_array(client: TestClient) -> None:
    resp = client.get("/api/backtest/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_backtest_post_returns_202_with_job_id(client: TestClient) -> None:
    payload = {
        "market": "KRW-BTC",
        "period_from": "2025-01-01",
        "period_to": "2025-06-30",
        "mode": "both",
    }
    resp = client.post("/api/backtest/jobs", json=payload)
    assert resp.status_code == 202
    assert "job_id" in resp.json()


def test_backtest_get_job_by_id_returns_view_or_404(client: TestClient) -> None:
    resp = client.get("/api/backtest/jobs/nonexistent-id")
    assert resp.status_code in (200, 404)


# ── Daemon ─────────────────────────────────────────────────────────────────

def test_daemon_status_initially_false(client: TestClient) -> None:
    resp = client.get("/api/daemon/status")
    assert resp.status_code == 200
    assert resp.json()["running"] is False


def test_daemon_start_returns_202(client: TestClient) -> None:
    resp = client.post("/api/daemon/start")
    assert resp.status_code == 202


def test_daemon_stop_returns_202(client: TestClient) -> None:
    # 실행 중이어야 정지 가능 → start 후 stop
    client.post("/api/daemon/start")
    resp = client.post("/api/daemon/stop")
    assert resp.status_code == 202


# ── Dashboard ──────────────────────────────────────────────────────────────

def test_dashboard_aggregates_health_settings_and_daemon(client: TestClient) -> None:
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "daemon_status" in data


# ── Security (unit-level) ──────────────────────────────────────────────────

def test_mask_secrets_replaces_known_secret_keys() -> None:
    from signal_program.web.security import mask_secret_value

    masked = mask_secret_value("1234567890:AABCDEFGHIJKLMNOP")
    assert "AABCDEFGHIJKLMNOP" not in masked
    assert "•" in masked or "*" in masked


def test_assert_safe_bind_blocks_zero_zero_without_password() -> None:
    from signal_program.web.security import assert_safe_bind

    with pytest.raises(SystemExit):
        assert_safe_bind("0.0.0.0", "")


def test_assert_safe_bind_allows_localhost_without_password() -> None:
    from signal_program.web.security import assert_safe_bind

    assert_safe_bind("127.0.0.1", "")  # should not raise


def test_assert_safe_bind_allows_external_with_password() -> None:
    from signal_program.web.security import assert_safe_bind

    assert_safe_bind("0.0.0.0", "secret123")  # should not raise
