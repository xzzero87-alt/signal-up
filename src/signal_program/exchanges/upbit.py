from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from datetime import datetime

    from signal_program.enums import Timeframe
    from signal_program.models import Candle

log = structlog.get_logger()
_BASE_URL = "https://api.upbit.com"
_KST = ZoneInfo("Asia/Seoul")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.NetworkError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


def _log_rate_limit(resp: httpx.Response, market: str = "") -> None:
    if remaining := resp.headers.get("Remaining-Req"):
        log.debug("upbit.rate_limit", remaining_req=remaining, market=market)


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

    async def _get(self, path: str, *, _market_tag: str = "", **params: Any) -> httpx.Response:
        """세마포어 + 지수 백오프 재시도로 GET 요청."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                async with self._sem:
                    resp = await self._client.get(path, params=params)
                    _log_rate_limit(resp, market=_market_tag)
                    if resp.status_code in {429, 500, 502, 503, 504}:
                        resp.raise_for_status()
                    return resp
        raise AssertionError("unreachable")  # reraise=True guarantees exception propagation

    async def list_krw_markets(self) -> list[str]:
        resp = await self._get("/v1/market/all", isDetails="false")
        return [item["market"] for item in resp.json() if item["market"].startswith("KRW-")]

    async def fetch_candles(
        self,
        market: str,
        timeframe: Timeframe,
        count: int,
        to: datetime | None = None,
    ) -> list[Candle]:
        from datetime import datetime as _dt

        from signal_program.models import Candle as CandleModel

        params: dict[str, Any] = {"market": market, "count": count}
        if to is not None:
            params["to"] = to.strftime("%Y-%m-%dT%H:%M:%S")

        unit = str(timeframe)  # Timeframe.HOUR_1 → "60"
        resp = await self._get(f"/v1/candles/minutes/{unit}", _market_tag=market, **params)

        return [
            CandleModel(
                market=raw["market"],
                opened_at=_dt.fromisoformat(raw["candle_date_time_kst"]).replace(tzinfo=_KST),
                open=float(raw["opening_price"]),
                high=float(raw["high_price"]),
                low=float(raw["low_price"]),
                close=float(raw["trade_price"]),
                volume=float(raw["candle_acc_trade_volume"]),
                quote_volume=float(raw["candle_acc_trade_price"]),
            )
            for raw in resp.json()
        ]

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> UpbitClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
