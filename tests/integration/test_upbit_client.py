"""업비트 REST 클라이언트 통합 테스트.

TDD Phase 1 RED  : NotImplementedError로 계약 위반 확인
TDD Phase 2 GREEN: VCR 카세트 녹화 → 통과
TDD Phase 3      : 429/재시도/동시성 MockTransport 검증
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

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
# d) 429 재시도 — Phase 3에서 MockTransport로 구현
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Phase 3에서 구현 — 429 재시도 MockTransport 테스트")
async def test_fetch_candles_429_retry() -> None:
    pass
