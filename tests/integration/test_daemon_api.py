"""데몬 API 통합 테스트 — M16 Phase 1 RED."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from signal_program.web.app import create_app
    from signal_program.web.runner_handle import RunnerHandle

    async def fake_runner() -> None:
        await asyncio.sleep(100)

    handle = RunnerHandle(runner_factory=fake_runner, stop_grace_sec=0.5)
    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
        runner_handle=handle,
    )
    with TestClient(app) as c:
        yield c


def test_daemon_status_initial_stopped(client: TestClient) -> None:
    resp = client.get("/api/daemon/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is False
    assert data["started_at"] is None


def test_daemon_start_returns_202_and_runs(client: TestClient) -> None:
    resp = client.post("/api/daemon/start")
    assert resp.status_code == 202
    status = client.get("/api/daemon/status").json()
    assert status["running"] is True
    client.post("/api/daemon/stop")


def test_daemon_start_twice_returns_409_korean(client: TestClient) -> None:
    client.post("/api/daemon/start")
    resp = client.post("/api/daemon/start")
    assert resp.status_code == 409
    detail = resp.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "이미 실행 중" in msg
    client.post("/api/daemon/stop")


def test_daemon_stop_returns_202(client: TestClient) -> None:
    client.post("/api/daemon/start")
    resp = client.post("/api/daemon/stop")
    assert resp.status_code == 202
    status = client.get("/api/daemon/status").json()
    assert status["running"] is False


def test_daemon_stop_twice_returns_409_korean(client: TestClient) -> None:
    resp = client.post("/api/daemon/stop")
    assert resp.status_code == 409
    detail = resp.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "이미 정지" in msg


def test_dashboard_header_shows_running_state_after_start(client: TestClient) -> None:
    client.post("/api/daemon/start")
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["daemon_status"] == "running"
    client.post("/api/daemon/stop")
