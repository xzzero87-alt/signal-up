"""HTML 페이지 렌더링 통합 테스트 — M14."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from signal_program.web.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(settings_path=tmp_path / "settings.json")
    return TestClient(app)


def test_get_root_returns_dashboard_html(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "<title>" in resp.text.lower() or "<!doctype" in resp.text.lower()


def test_get_settings_page_returns_html(client: TestClient) -> None:
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_dashboard_html_contains_polling_script(client: TestClient) -> None:
    resp = client.get("/")
    assert "POLL_INTERVAL_MS" in resp.text or "setInterval" in resp.text


def test_settings_html_contains_help_tooltips_for_all_settings(client: TestClient) -> None:
    from signal_program.web.help_text import SETTING_HELP

    resp = client.get("/settings")
    for key in SETTING_HELP:
        assert key in resp.text, f"도움말 키 없음: {key}"


def test_static_css_served(client: TestClient) -> None:
    resp = client.get("/static/css/app.css")
    assert resp.status_code == 200


def test_no_external_cdn_in_html(client: TestClient) -> None:
    for path in ("/", "/settings"):
        resp = client.get(path)
        for banned in ("https://cdn.", "http://cdn.", "googleapis.com", "jsdelivr.net"):
            assert banned not in resp.text, f"외부 CDN 발견 in {path}: {banned}"


def test_dashboard_warning_shown_when_daemon_stub(client: TestClient) -> None:
    resp = client.get("/")
    assert "M16" in resp.text or "데몬 제어" in resp.text
