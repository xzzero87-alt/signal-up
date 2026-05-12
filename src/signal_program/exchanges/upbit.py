from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from datetime import datetime

    from signal_program.enums import Timeframe
    from signal_program.models import Candle

log = structlog.get_logger()
_BASE_URL = "https://api.upbit.com"


class UpbitClient:
    """업비트 REST API 클라이언트 (공개 API 전용 — 인증 없음).

    Rate-limit 정책 (DESIGN.md §4.1):
      - IP 당 ~10 req/sec, ~600 req/min
      - Remaining-Req 헤더 → structlog DEBUG 로그 (cycle_id·market 상관 키 포함)
      - asyncio.Semaphore(5) 동시 요청 제한
      - 재시도: 5xx/429/NetworkError → 지수 백오프 1s→2s→4s (max 10s), 최대 3회
    """

    def __init__(self, *, _client: httpx.AsyncClient | None = None) -> None:
        self._client = _client or httpx.AsyncClient(base_url=_BASE_URL, timeout=10.0)
        self._sem = asyncio.Semaphore(5)

    async def list_krw_markets(self) -> list[str]:
        raise NotImplementedError

    async def fetch_candles(
        self,
        market: str,
        timeframe: Timeframe,
        count: int,
        to: datetime | None = None,
    ) -> list[Candle]:
        raise NotImplementedError

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> UpbitClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
