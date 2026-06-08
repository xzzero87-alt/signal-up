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


# ── 국장 큐레이션 (/api/markets/kr) ──────────────────────────────────────────


def test_kr_returns_curated_universe(client: TestClient) -> None:
    resp = client.get("/api/markets/kr")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 43  # §4 시작목록
    sample = data[0]
    assert set(sample) == {"code", "name", "market", "sector"}
    assert all(item["market"] in {"KOSPI", "KOSDAQ"} for item in data)
    assert all(len(item["code"]) == 6 and item["code"].isdigit() for item in data)
    codes = [item["code"] for item in data]
    assert len(codes) == len(set(codes))  # 코드 중복 없음


def test_kr_altteogen_is_kospi(client: TestClient) -> None:
    """알테오젠(196170) KOSDAQ→KOSPI 이전 반영 확인."""
    data = client.get("/api/markets/kr").json()
    altteogen = next(item for item in data if item["code"] == "196170")
    assert altteogen["market"] == "KOSPI"


def test_kr_kosdaq_subset(client: TestClient) -> None:
    data = client.get("/api/markets/kr").json()
    kosdaq = {item["code"] for item in data if item["market"] == "KOSDAQ"}
    # 에코프로비엠·에코프로·HLB·펄어비스·카카오게임즈·에스엠·JYP
    assert kosdaq == {"247540", "086520", "028300", "263750", "293490", "041510", "035900"}
