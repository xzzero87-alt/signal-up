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


def test_put_settings_bulk_whitelist_round_trip(client: TestClient) -> None:
    """대량 선택(멀티셀렉트) 코인 배열이 순서·전량 그대로 라운드트립 (v2.2 M5)."""
    markets = [f"KRW-T{i:02d}" for i in range(40)]
    resp = client.put("/api/settings", json={"whitelist_markets": markets})
    assert resp.status_code == 200, resp.text
    assert resp.json()["whitelist_markets"] == markets


def test_put_settings_bulk_kr_symbols_round_trip(client: TestClient) -> None:
    """대량 선택(멀티셀렉트) 국장 배열이 순서·전량 그대로 라운드트립 (v2.2 M5)."""
    symbols = [f"{i:06d}" for i in range(1, 41)]
    resp = client.put("/api/settings", json={"kr_whitelist_symbols": symbols})
    assert resp.status_code == 200, resp.text
    assert list(resp.json()["kr_whitelist_symbols"]) == symbols


def test_put_settings_empty_coin_with_kr_returns_200(client: TestClient) -> None:
    """코인 화이트리스트가 비어도 국장 종목이 있으면 200 (v2.2 M2)."""
    resp = client.put(
        "/api/settings",
        json={"whitelist_markets": [], "kr_whitelist_symbols": ["005930"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["whitelist_markets"] == []
    assert "005930" in data["kr_whitelist_symbols"]


def test_put_settings_both_empty_returns_422(client: TestClient) -> None:
    """코인·국장 둘 다 비면 422 (v2.2 M2)."""
    resp = client.put(
        "/api/settings",
        json={"whitelist_markets": [], "kr_whitelist_symbols": []},
    )
    assert resp.status_code == 422, resp.text


def test_put_settings_both_empty_korean_message(client: TestClient) -> None:
    """둘 다 빈 422 응답에 한국어 메시지, 영어 prefix 없어야 한다."""
    resp = client.put(
        "/api/settings",
        json={"whitelist_markets": [], "kr_whitelist_symbols": []},
    )
    assert resp.status_code == 422
    data = resp.json()
    detail = data.get("detail", [])
    assert isinstance(detail, list) and detail, "detail이 비어있음"

    all_messages = " ".join(e.get("message", "") for e in detail)
    assert "화이트리스트" in all_messages, f"한국어 메시지 없음: {all_messages}"
    assert "Value error" not in all_messages, f'"Value error" 영어 prefix 노출: {all_messages}'
    assert "tuple" not in all_messages, f'"tuple" 타입 이름 노출: {all_messages}'
