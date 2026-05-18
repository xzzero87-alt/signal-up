"""HTML 페이지 렌더링 통합 테스트 — M14."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from signal_program.web.app import create_app


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    def _noop(spec: object, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>ok</html>", encoding="utf-8")

    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
        _job_executor=_noop,
    )
    with TestClient(app) as c:
        yield c


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


def test_dashboard_has_daemon_toggle_in_nav(client: TestClient) -> None:
    """M16 이후: 헤더에 실제 데몬 토글 버튼이 있어야 한다 (stub 안내문 대체)."""
    resp = client.get("/")
    assert "nav-daemon-btn" in resp.text or "toggleDaemon" in resp.text


def test_dashboard_html_no_stub_m16_message(client: TestClient) -> None:
    """결함 2 회귀: 'M16에서 활성화됩니다' stub 안내 박스가 제거되어야 한다."""
    resp = client.get("/")
    assert "M16에서 활성화됩니다" not in resp.text


def test_dashboard_html_loads_only_dashboard_js(client: TestClient) -> None:
    """결함 1 회귀: 대시보드 페이지는 dashboard.js만 로드해야 한다."""
    resp = client.get("/")
    assert "dashboard.js" in resp.text
    assert "backtest.js" not in resp.text
    assert "settings.js" not in resp.text


def test_backtest_html_loads_only_backtest_js(client: TestClient) -> None:
    """결함 1 회귀: 백테스트 페이지는 backtest.js만 로드해야 한다."""
    resp = client.get("/backtest")
    assert "backtest.js" in resp.text
    assert "dashboard.js" not in resp.text
    assert "settings.js" not in resp.text


def test_settings_html_loads_only_settings_js(client: TestClient) -> None:
    """결함 1 회귀: 설정 페이지는 settings.js만 로드해야 한다."""
    resp = client.get("/settings")
    assert "settings.js" in resp.text
    assert "dashboard.js" not in resp.text
    assert "backtest.js" not in resp.text


def test_dashboard_js_no_duplicate_const_declaration() -> None:
    """결함 1 회귀: dashboard.js에 POLL_INTERVAL_MS const 중복 선언이 없어야 한다."""
    import pathlib
    import re

    js = pathlib.Path(__file__).parents[2] / "src" / "signal_program" / "web" / "static" / "js" / "dashboard.js"
    text = js.read_text(encoding="utf-8")
    # 'const POLL_INTERVAL_MS' 선언이 있으면 중복 — index.html 인라인에만 있어야 함
    assert not re.search(r"const\s+POLL_INTERVAL_MS", text), (
        "dashboard.js에 const POLL_INTERVAL_MS 중복 선언 — index.html inline과 충돌"
    )
