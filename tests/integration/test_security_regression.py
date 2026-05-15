"""보안 회귀 테스트 — M13 회귀 + M16 신규 (M16 Phase 1 RED)."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _basic_header(user: str, pw: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from signal_program.web.app import create_app

    app = create_app(settings_path=tmp_path / "settings.json")
    with TestClient(app) as c:
        yield c


# ── M13 회귀 ─────────────────────────────────────────────────────────────────


def test_zero_zero_zero_zero_without_password_raises_systemexit() -> None:
    from signal_program.web.security import assert_safe_bind

    with pytest.raises(SystemExit):
        assert_safe_bind("0.0.0.0", None)


def test_localhost_without_password_is_allowed() -> None:
    from signal_program.web.security import assert_safe_bind

    assert_safe_bind("127.0.0.1", None)


def test_token_masked_in_settings_response(client: TestClient) -> None:
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert "telegram_bot_token_masked" in resp.text


# ── M16 신규 ─────────────────────────────────────────────────────────────────


def test_zero_zero_zero_zero_with_password_no_systemexit() -> None:
    from signal_program.web.security import assert_safe_bind

    assert_safe_bind("0.0.0.0", "strong-password-here")


def test_correct_password_can_change_settings(tmp_path: Path) -> None:
    from signal_program.web.app import create_app
    from signal_program.web.middleware import BasicAuthMiddleware

    app = create_app(settings_path=tmp_path / "settings.json")
    app.add_middleware(BasicAuthMiddleware, bind="0.0.0.0", password="correct-pw")
    with TestClient(app) as c:
        resp = c.put(
            "/api/settings",
            json={"dry_run": True},
            headers={"Authorization": _basic_header("admin", "correct-pw")},
        )
        assert resp.status_code == 200


def test_no_auth_header_blocks_settings_put(tmp_path: Path) -> None:
    from signal_program.web.app import create_app
    from signal_program.web.middleware import BasicAuthMiddleware

    app = create_app(settings_path=tmp_path / "settings.json")
    app.add_middleware(BasicAuthMiddleware, bind="0.0.0.0", password="secret")
    with TestClient(app) as c:
        resp = c.put("/api/settings", json={"dry_run": True})
        assert resp.status_code == 401


def test_no_auth_header_blocks_daemon_start(tmp_path: Path) -> None:
    from signal_program.web.app import create_app
    from signal_program.web.middleware import BasicAuthMiddleware

    app = create_app(settings_path=tmp_path / "settings.json")
    app.add_middleware(BasicAuthMiddleware, bind="0.0.0.0", password="secret")
    with TestClient(app) as c:
        resp = c.post("/api/daemon/start")
        assert resp.status_code == 401


def test_no_auth_header_blocks_backtest_post(tmp_path: Path) -> None:
    from signal_program.web.app import create_app
    from signal_program.web.middleware import BasicAuthMiddleware

    app = create_app(settings_path=tmp_path / "settings.json")
    app.add_middleware(BasicAuthMiddleware, bind="0.0.0.0", password="secret")
    with TestClient(app) as c:
        resp = c.post(
            "/api/backtest/jobs",
            json={"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"},
        )
        assert resp.status_code == 401
