"""설정 폼 ↔ 스키마/전략 패널 일관성 회귀 가드.

- BUG-1 가드: settings.html 폼의 모든 input name이 SettingsUpdate 필드에 존재해야 한다.
  (누락 시 extra="forbid"로 PUT이 422가 되어 UI 저장이 통째로 무력화됨)
- BUG-3 가드: 저장된 전략에 해당하는 파라미터 패널만 표시되고, 카드 강조도 하나만.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path

import pytest
import signal_program.web
from fastapi.testclient import TestClient

from signal_program.web.app import create_app
from signal_program.web.help_text import SETTING_HELP
from signal_program.web.schemas import SettingsUpdate


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


def test_all_param_fields_have_help_text(client: TestClient) -> None:
    """settings.html data-field 입력이 SETTING_HELP에 누락 없이 존재해야 함 (v2.6 재발 방지)."""
    resp = client.get("/settings")
    assert resp.status_code == 200
    field_names = set(re.findall(r'data-field="([a-zA-Z0-9_]+)"', resp.text))
    missing = sorted(f for f in field_names if f not in SETTING_HELP or not SETTING_HELP[f])
    assert not missing, (
        f"settings.html data-field가 SETTING_HELP에 없거나 비어있음: {missing}"
    )


# ── Task 2: JS 타입 집합 ↔ SettingsUpdate 타입 drift 가드 ──────────────────────


def _parse_js_type_sets(js_path: Path) -> dict[str, set[str]]:
    """settings.js에서 INT_FIELDS / FLOAT_FIELDS / STRING_FIELDS / CHECKBOX_FIELDS 파싱."""
    content = js_path.read_text(encoding="utf-8")
    result: dict[str, set[str]] = {}
    for m in re.finditer(
        r"const\s+(INT_FIELDS|FLOAT_FIELDS|STRING_FIELDS|CHECKBOX_FIELDS)"
        r"\s*=\s*new\s+Set\(\[([\s\S]*?)\]\)",
        content,
    ):
        result[m.group(1)] = set(re.findall(r"'([a-z0-9_]+)'", m.group(2)))
    return result


def _schema_type_map() -> dict[str, set[str]]:
    """SettingsUpdate 필드를 int / float / str / bool 타입별로 분류.

    list[str] 필드(whitelist_markets 등)와 Literal 필드(strategy_version)는 제외.
    """
    int_f: set[str] = set()
    float_f: set[str] = set()
    str_f: set[str] = set()
    bool_f: set[str] = set()

    for name, field_info in SettingsUpdate.model_fields.items():
        ann = field_info.annotation
        args = typing.get_args(ann)
        non_none = [a for a in args if a is not type(None)]
        base = non_none[0] if non_none else ann

        if typing.get_origin(base) is list:
            continue
        if typing.get_origin(base) is typing.Literal:
            continue

        if base is bool:
            bool_f.add(name)
        elif base is int:
            int_f.add(name)
        elif base is float:
            float_f.add(name)
        elif base is str:
            str_f.add(name)

    return {
        "INT_FIELDS": int_f,
        "FLOAT_FIELDS": float_f,
        "STRING_FIELDS": str_f,
        "CHECKBOX_FIELDS": bool_f,
    }


def test_kr_strategy_radio_exists_and_checked(client: TestClient) -> None:
    """settings.html에 kr_strategy radio 2개 존재 + 저장된 값에 checked."""
    assert client.put("/api/settings", json={"kr_strategy": "bb_cci"}).status_code == 200
    html = client.get("/settings").text
    form = _form_html(html, "settings-form")
    radio_tags = re.findall(r'<input[^>]+name="kr_strategy"[^>]*>', form)
    assert len(radio_tags) == 2, f"kr_strategy radio가 2개가 아님: {len(radio_tags)}"
    checked = [t for t in radio_tags if "checked" in t]
    assert len(checked) == 1, f"checked radio가 1개가 아님: {checked}"
    assert 'value="bb_cci"' in checked[0], f"checked가 bb_cci가 아님: {checked[0]}"


def test_dashboard_kr_strategy_reflects_settings(client: TestClient) -> None:
    """PUT kr_strategy=bb_cci → /api/dashboard settings_summary.kr_strategy == 'bb_cci'."""
    assert client.put("/api/settings", json={"kr_strategy": "bb_cci"}).status_code == 200
    data = client.get("/api/dashboard").json()
    assert data["settings_summary"]["kr_strategy"] == "bb_cci"


def test_js_type_sets_match_schema() -> None:
    """JS 타입 집합 ↔ SettingsUpdate 필드 타입 양방향 일치 가드 (타입 drift 차단)."""
    js_path = Path(signal_program.web.__file__).parent / "static" / "js" / "settings.js"
    js_sets = _parse_js_type_sets(js_path)
    schema_map = _schema_type_map()
    all_schema_fields = set(SettingsUpdate.model_fields)

    for set_name, schema_fields in schema_map.items():
        js_fields = js_sets.get(set_name, set())

        # ① 스키마 → JS: 스키마 필드가 해당 JS 집합에 없으면 브라우저가 잘못된 타입으로 전송
        missing_in_js = sorted(schema_fields - js_fields)
        assert not missing_in_js, (
            f"{set_name}: SettingsUpdate 필드가 JS 집합에 없음 → 타입 변환 누락: {missing_in_js}"
        )

        # ② JS → 스키마: JS 집합 항목이 SettingsUpdate에 없으면 오타·죽은 항목
        dead_in_js = sorted(js_fields - all_schema_fields)
        assert not dead_in_js, (
            f"{set_name}: JS 집합 항목이 SettingsUpdate에 없음 → 오타·죽은 항목: {dead_in_js}"
        )
