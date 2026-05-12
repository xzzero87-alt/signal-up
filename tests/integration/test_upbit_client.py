"""업비트 REST 클라이언트 통합 테스트.

TDD Phase 1 RED  : NotImplementedError로 계약 위반 확인
TDD Phase 2 GREEN: VCR 카세트 녹화 → 통과
TDD Phase 3      : 429/재시도/동시성 MockTransport 검증
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from zoneinfo import ZoneInfo

import httpx
import pytest

from signal_program.enums import Timeframe
from signal_program.exchanges.upbit import UpbitClient

pytestmark = pytest.mark.anyio

_KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# a) KRW 마켓 목록
# ---------------------------------------------------------------------------


@pytest.mark.vcr
async def test_list_krw_markets() -> None:
    async with UpbitClient() as client:
        markets = await client.list_krw_markets()
    assert len(markets) >= 100
    assert all(m.startswith("KRW-") for m in markets)


# ---------------------------------------------------------------------------
# b) 1시간봉 200개, timezone-aware KST
# ---------------------------------------------------------------------------


@pytest.mark.vcr
async def test_fetch_candles_200() -> None:
    async with UpbitClient() as client:
        candles = await client.fetch_candles("KRW-BTC", Timeframe.HOUR_1, 200)
    assert len(candles) == 200
    assert candles[0].opened_at.tzinfo == _KST


# ---------------------------------------------------------------------------
# c) 빈 결과 — Upbit 개장(2017) 이전 날짜로 조회
# ---------------------------------------------------------------------------


@pytest.mark.vcr
async def test_fetch_candles_empty() -> None:
    before_upbit = dt.datetime(2016, 1, 1, tzinfo=dt.UTC)
    async with UpbitClient() as client:
        candles = await client.fetch_candles("KRW-BTC", Timeframe.HOUR_1, 200, to=before_upbit)
    assert candles == []


# ---------------------------------------------------------------------------
# d) 429 재시도 — _SequentialTransport MockTransport 기반 (아래 Phase 3 참조)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 3: 429 → 재시도 → 최종 성공 (MockTransport)
# ---------------------------------------------------------------------------


class _SequentialTransport(httpx.AsyncBaseTransport):
    """순서대로 응답을 반환하는 테스트용 트랜스포트."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._queue = list(responses)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self._queue.pop(0)


async def test_429_retry_eventually_succeeds() -> None:
    payload = json.dumps([{"market": "KRW-BTC"}, {"market": "KRW-ETH"}]).encode()
    transport = _SequentialTransport(
        [
            httpx.Response(429, headers={"Remaining-Req": "group=market; min=0; sec=0"}),
            httpx.Response(429, headers={"Remaining-Req": "group=market; min=0; sec=0"}),
            httpx.Response(200, content=payload),
        ]
    )
    mock_client = httpx.AsyncClient(base_url="https://api.upbit.com", transport=transport)
    upbit = UpbitClient(_client=mock_client)
    try:
        markets = await upbit.list_krw_markets()
    finally:
        await upbit.aclose()
    assert markets == ["KRW-BTC", "KRW-ETH"]


# ---------------------------------------------------------------------------
# Phase 3: Semaphore(5) 동시성 제한 검증
# ---------------------------------------------------------------------------


async def test_semaphore_limits_max_concurrency() -> None:
    current: list[int] = [0]
    peak: list[int] = [0]

    class _CountingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            current[0] += 1
            peak[0] = max(peak[0], current[0])
            await asyncio.sleep(0.02)
            current[0] -= 1
            return httpx.Response(200, content=b"[]")

    mock_client = httpx.AsyncClient(
        base_url="https://api.upbit.com", transport=_CountingTransport()
    )
    upbit = UpbitClient(_client=mock_client)
    try:
        await asyncio.gather(*[upbit.list_krw_markets() for _ in range(10)])
    finally:
        await upbit.aclose()

    assert peak[0] <= 5, f"동시 요청이 Semaphore(5)를 초과: {peak[0]}"
