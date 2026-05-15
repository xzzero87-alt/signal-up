"""BasicAuthMiddleware 통합 테스트 — M16 Phase 1 RED."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _basic_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


@pytest.fixture
def localhost_client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from signal_program.web.app import create_app

    app = create_app(settings_path=tmp_path / "settings.json")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def external_client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from signal_program.web.app import create_app
    from signal_program.web.middleware import BasicAuthMiddleware

    app = create_app(settings_path=tmp_path / "settings.json")
    app.add_middleware(BasicAuthMiddleware, bind="0.0.0.0", password="test-secret-pw")
    with TestClient(app) as c:
        yield c


def test_localhost_request_bypasses_auth(localhost_client: TestClient) -> None:
    resp = localhost_client.get("/api/health")
    assert resp.status_code == 200


def test_external_bind_requires_basic_auth(external_client: TestClient) -> None:
    resp = external_client.get("/api/health")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_external_bind_accepts_correct_password(external_client: TestClient) -> None:
    resp = external_client.get(
        "/api/health",
        headers={"Authorization": _basic_header("admin", "test-secret-pw")},
    )
    assert resp.status_code == 200


def test_external_bind_rejects_wrong_password(external_client: TestClient) -> None:
    resp = external_client.get(
        "/api/health",
        headers={"Authorization": _basic_header("admin", "wrong-password")},
    )
    assert resp.status_code == 401


def test_auth_uses_constant_time_comparison() -> None:
    """middleware.py 소스에 secrets.compare_digest 호출이 있어야 한다."""
    import pathlib

    src = pathlib.Path(__file__).parents[3] / "src" / "signal_program" / "web" / "middleware.py"
    assert src.exists(), "middleware.py 파일이 없습니다"
    text = src.read_text(encoding="utf-8")
    assert "secrets.compare_digest" in text, "timing-safe 비교가 없습니다"
