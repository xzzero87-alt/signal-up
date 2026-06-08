"""v2.2 M1 — GET /api/markets/coins 통합 테스트.

업비트 호출은 FakeUpbit로 대체(dependency override). 200·KRW목록·1h 캐시 검증.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from signal_program.web.api import markets
from signal_program.web.app import create_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


class FakeUpbit:
    """list_krw_markets_detailed만 흉내내는 가짜 클라이언트. 호출 횟수 기록."""

    def __init__(self) -> None:
        self.calls = 0

    async def list_krw_markets_detailed(self) -> list[dict[str, str]]:
        self.calls += 1
        return [
            {"market": "KRW-BTC", "korean_name": "비트코인"},
            {"market": "KRW-ETH", "korean_name": "이더리움"},
        ]


@pytest.fixture
def fake_upbit() -> FakeUpbit:
    return FakeUpbit()


@pytest.fixture
def client(tmp_path: Path, fake_upbit: FakeUpbit):  # type: ignore[no-untyped-def]
    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
    )

    async def _fake_client() -> AsyncIterator[FakeUpbit]:
        yield fake_upbit

    app.dependency_overrides[markets.get_upbit_client] = _fake_client
    markets.clear_coins_cache()
    with TestClient(app) as c:
        yield c
    markets.clear_coins_cache()


def test_coins_returns_krw_markets(client: TestClient) -> None:
    resp = client.get("/api/markets/coins")
    assert resp.status_code == 200
    data = resp.json()
    assert data == [
        {"market": "KRW-BTC", "korean_name": "비트코인"},
        {"market": "KRW-ETH", "korean_name": "이더리움"},
    ]
    assert all(item["market"].startswith("KRW-") for item in data)


def test_coins_cached_within_ttl(client: TestClient, fake_upbit: FakeUpbit) -> None:
    client.get("/api/markets/coins")
    client.get("/api/markets/coins")
    assert fake_upbit.calls == 1  # 두 번째 요청은 캐시 히트
