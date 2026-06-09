"""설정 폼 ↔ 스키마/전략 패널 일관성 회귀 가드.

- BUG-1 가드: settings.html 폼의 모든 input name이 SettingsUpdate 필드에 존재해야 한다.
  (누락 시 extra="forbid"로 PUT이 422가 되어 UI 저장이 통째로 무력화됨)
- BUG-3 가드: 저장된 전략에 해당하는 파라미터 패널만 표시되고, 카드 강조도 하나만.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from signal_program.web.app import create_app
from signal_program.web.schemas import SettingsUpdate
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
    )
    with TestClient(app) as c:
        yield c


def _form_html(html: str, form_id: str) -> str:
    start = html.index(f'<form id="{form_id}"')
    end = html.index("</form>", start)
    return html[start:end]


def _input_names(form_html: str) -> set[str]:
    return set(re.findall(r'name="([a-zA-Z0-9_]+)"', form_html))


def test_all_settings_form_inputs_have_schema_field(client: TestClient) -> None:
    """폼의 모든 input이 SettingsUpdate에 존재 — 누락 시 저장 전체가 422로 깨짐(BUG-1)."""
    resp = client.get("/settings")
    assert resp.status_code == 200
    names = _input_names(_form_html(resp.text, "settings-form"))
    schema_fields = set(SettingsUpdate.model_fields)
    missing = sorted(n for n in names if n not in schema_fields)
    assert not missing, (
        f"settings.html 폼 input이 SettingsUpdate에 없음 → PUT 422로 저장 무력화: {missing}"
    )


def test_all_system_form_inputs_have_schema_field(client: TestClient) -> None:
    """시스템 페이지 폼 input도 SettingsUpdate에 존재해야 함 (v2.2 M4 두 번째 폼, BUG-1)."""
    resp = client.get("/system")
    assert resp.status_code == 200
    names = _input_names(_form_html(resp.text, "system-settings-form"))
    schema_fields = set(SettingsUpdate.model_fields)
    missing = sorted(n for n in names if n not in schema_fields)
    assert not missing, (
        f"system.html 폼 input이 SettingsUpdate에 없음 → PUT 422로 저장 무력화: {missing}"
    )


def _panel_hidden(html: str, panel_id: str) -> bool:
    """id=panel_id 인 div 태그에 display:none 이 있으면 숨김."""
    m = re.search(r'id="' + re.escape(panel_id) + r'"[^>]*>', html)
    assert m, f"패널 없음: {panel_id}"
    return "display:none" in m.group(0)


def _card_on(html: str, card_id: str) -> bool:
    m = re.search(r'<label class="strat-card([^"]*)" id="' + re.escape(card_id) + r'"', html)
    assert m, f"카드 없음: {card_id}"
    return " on" in m.group(1) or m.group(1).strip() == "on"


_PANEL = {
    "v1": "v1-params",
    "v2": "v2-section",
    "v3": "v3-params",
    "v4": "v4-params",
    "v5": "v5-params",
}


@pytest.mark.parametrize("ver", ["v1", "v2", "v3", "v4", "v5"])
def test_only_selected_strategy_panel_visible(client: TestClient, ver: str) -> None:
    """저장된 전략의 패널만 표시 + 카드도 하나만 강조 (BUG-3)."""
    assert client.put("/api/settings", json={"strategy_version": ver}).status_code == 200
    html = client.get("/settings").text

    for v, pid in _PANEL.items():
        hidden = _panel_hidden(html, pid)
        if v == ver:
            assert not hidden, f"{ver} 선택인데 {pid} 패널이 숨겨짐"
        else:
            assert hidden, f"{ver} 선택인데 {pid} 패널이 함께 표시됨"

    on_cards = [v for v in _PANEL if _card_on(html, f"card-{v}")]
    assert on_cards == [ver], f"{ver} 선택인데 강조된 카드: {on_cards}"
