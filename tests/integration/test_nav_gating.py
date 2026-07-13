"""GUI 표면 게이팅 — 활성 전략에 맞춰 사이드바·랜딩을 정리 (ADR-0028 P1).

라이브 표면만 플래그로 숨긴다(엔진·백테스트·API 라우터는 보존). 플래그를 켜면 표면이
그대로 되살아나야 한다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from signal_program.web.app import create_app

if TYPE_CHECKING:
    from pathlib import Path

_DASH_LINK = 'href="/" class="sb-item'
_MOMENTUM_LINK = 'href="/momentum" class="sb-item'


def _make_client(tmp_path: Path, **flags: bool) -> TestClient:
    def _noop(spec: object, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>ok</html>", encoding="utf-8")

    # 세 플래그를 명시 고정 — 리포 .env 상태와 무관하게 결정론적.
    payload = {"coin_enabled": False, "kr_enabled": False, "momentum_enabled": False}
    payload.update(flags)
    (tmp_path / "settings.json").write_text(json.dumps(payload), encoding="utf-8")

    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
        _job_executor=_noop,
    )
    return TestClient(app)


def test_momentum_only_hides_bar_dashboard_in_sidebar(tmp_path: Path) -> None:
    """모멘텀만 활성 → 사이드바에 봉단위 대시보드 링크 없음, 모멘텀 링크만."""
    with _make_client(tmp_path, momentum_enabled=True) as client:
        html = client.get("/settings").text
    assert _DASH_LINK not in html, "모멘텀-only인데 봉단위 대시보드 링크가 사이드바에 있음"
    assert _MOMENTUM_LINK in html, "모멘텀 링크가 사이드바에 없음"


def test_momentum_only_landing_redirects_to_momentum(tmp_path: Path) -> None:
    """모멘텀만 활성 → `/`가 /momentum으로 리다이렉트(봉단위 대시보드 렌더 안 함)."""
    with _make_client(tmp_path, momentum_enabled=True) as client:
        resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"].endswith("/momentum")


def test_momentum_surface_has_no_bar_premise_text(tmp_path: Path) -> None:
    """모멘텀 표면에는 봉단위 전제('1시간봉 마감') 문구가 없어야 한다."""
    with _make_client(tmp_path, momentum_enabled=True) as client:
        html = client.get("/momentum").text
    assert "1시간봉" not in html, "모멘텀 페이지에 봉단위 전제 문구('1시간봉')가 남아 있음"


def test_bar_enabled_shows_dashboard_hides_momentum(tmp_path: Path) -> None:
    """코인 봉단위만 활성 → 대시보드 링크 노출, 모멘텀 링크 숨김, `/`는 대시보드 렌더."""
    with _make_client(tmp_path, coin_enabled=True) as client:
        settings_html = client.get("/settings").text
        root = client.get("/", follow_redirects=False)
    assert _DASH_LINK in settings_html, "봉단위 활성인데 대시보드 링크가 없음"
    assert _MOMENTUM_LINK not in settings_html, "모멘텀 비활성인데 모멘텀 링크가 있음"
    assert root.status_code == 200, "봉단위 활성 시 `/`는 리다이렉트 없이 대시보드를 렌더해야 함"


def test_both_enabled_shows_both_links(tmp_path: Path) -> None:
    """코인+모멘텀 활성 → 대시보드·모멘텀 링크 모두 노출."""
    with _make_client(tmp_path, coin_enabled=True, momentum_enabled=True) as client:
        html = client.get("/settings").text
    assert _DASH_LINK in html
    assert _MOMENTUM_LINK in html


def test_backtest_always_visible_regardless_of_flags(tmp_path: Path) -> None:
    """백테스트 링크는 플래그와 무관하게 항상 노출(죽은 전략 재실험 보존)."""
    with _make_client(tmp_path, momentum_enabled=True) as client:
        html = client.get("/settings").text
    assert 'href="/backtest" class="sb-item' in html, "백테스트 링크가 항상 보여야 함"
