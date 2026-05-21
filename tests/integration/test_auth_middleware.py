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

    src = pathlib.Path(__file__).parents[2] / "src" / "signal_program" / "web" / "middleware.py"
    assert src.exists(), "middleware.py 파일이 없습니다"
    text = src.read_text(encoding="utf-8")
    assert "secrets.compare_digest" in text, "timing-safe 비교가 없습니다"


# ── create_app 미들웨어 자동 장착 (M16 Follow-up v4) ──────────────────────────


def test_create_app_with_external_bind_requires_auth(tmp_path: Path) -> None:
    """결함 회귀: create_app(bind='0.0.0.0') → BasicAuthMiddleware가 자동 장착되어 401 반환."""

    from signal_program.web.app import create_app

    app = create_app(
        settings_path=tmp_path / "settings.json",
        bind="0.0.0.0",
        web_auth_password="secret123",
    )
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 401, (
            "비-localhost bind 시 인증 없는 요청은 401이어야 한다 (BasicAuthMiddleware 미장착)"
        )


def test_create_app_with_external_bind_accepts_correct_password(tmp_path: Path) -> None:
    """결함 회귀: create_app(bind='0.0.0.0') + 올바른 비번 → 200."""

    from signal_program.web.app import create_app

    app = create_app(
        settings_path=tmp_path / "settings.json",
        bind="0.0.0.0",
        web_auth_password="secret123",
    )
    with TestClient(app) as client:
        resp = client.get(
            "/api/health",
            headers={"Authorization": _basic_header("admin", "secret123")},
        )
        assert resp.status_code == 200


def test_create_app_localhost_bind_no_auth_required(tmp_path: Path) -> None:
    """기본 localhost bind → BasicAuthMiddleware 비활성 → 인증 없어도 200."""

    from signal_program.web.app import create_app

    app = create_app(settings_path=tmp_path / "settings.json")
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
