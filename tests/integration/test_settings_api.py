"""settings API 통합 테스트 — Phase 2: RED.

결함 회귀: PUT /api/settings에 list 형태의 whitelist_markets 전달 시 200 반환.
빈 whitelist_markets 전달 시 422 + 한국어 메시지 + "Value error"/"tuple" 미노출.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from signal_program.web.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(settings_path=tmp_path / "settings.json")
    return TestClient(app)


def test_put_settings_whitelist_list_returns_200(client: TestClient) -> None:
    """list 형태의 whitelist_markets → 200."""
    resp = client.put(
        "/api/settings",
        json={"whitelist_markets": ["KRW-BTC", "KRW-ETH"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "whitelist_markets" in data
    assert isinstance(data["whitelist_markets"], list)
    assert "KRW-BTC" in data["whitelist_markets"]


def test_put_settings_whitelist_saved_as_list(tmp_path: Path) -> None:
    """settings.json에 whitelist_markets가 list로 저장되어야 한다."""
    import json

    settings_path = tmp_path / "settings.json"
    app = create_app(settings_path=settings_path)
    with TestClient(app) as c:
        resp = c.put(
            "/api/settings",
            json={"whitelist_markets": ["KRW-BTC", "KRW-SOL", "KRW-XRP"]},
        )
    assert resp.status_code == 200, resp.text
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert isinstance(saved["whitelist_markets"], list), (
        "settings.json에 whitelist_markets가 list가 아님"
    )
    assert saved["whitelist_markets"] == ["KRW-BTC", "KRW-SOL", "KRW-XRP"]


def test_put_settings_empty_whitelist_returns_422(client: TestClient) -> None:
    """빈 whitelist_markets → 422."""
    resp = client.put("/api/settings", json={"whitelist_markets": []})
    assert resp.status_code == 422, resp.text


def test_put_settings_empty_whitelist_korean_message(client: TestClient) -> None:
    """빈 whitelist_markets 422 응답에 한국어 메시지, 영어 prefix 없어야 한다."""
    resp = client.put("/api/settings", json={"whitelist_markets": []})
    assert resp.status_code == 422
    data = resp.json()
    detail = data.get("detail", [])
    assert isinstance(detail, list) and detail, "detail이 비어있음"

    all_messages = " ".join(e.get("message", "") for e in detail)
    assert "화이트리스트" in all_messages, f"한국어 메시지 없음: {all_messages}"
    assert "Value error" not in all_messages, f'"Value error" 영어 prefix 노출: {all_messages}'
    assert "tuple" not in all_messages, f'"tuple" 타입 이름 노출: {all_messages}'
