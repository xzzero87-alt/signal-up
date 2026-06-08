"""GET /api/markets/* — 설정 종목선택 UI용 마켓 데이터 소스 (v2.2 M1).

coins: 업비트 KRW 마켓 목록. 외부 호출 비용을 줄이기 위해 1시간 메모리 캐시.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from signal_program.data.kr_universe import KR_UNIVERSE
from signal_program.exchanges.upbit import UpbitClient
from signal_program.web.schemas import CoinMarket, KrUniverseStock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(tags=["markets"])

_KST = ZoneInfo("Asia/Seoul")
_COINS_CACHE_TTL = timedelta(hours=1)

# (만료 시각, 캐시된 목록). 모듈 전역 — 단일 이벤트 루프 기준 단순 캐시.
_coins_cache: tuple[datetime, list[CoinMarket]] | None = None


async def get_upbit_client() -> AsyncIterator[UpbitClient]:
    """요청 단위 UpbitClient 제공 (테스트 시 dependency override로 교체)."""
    client = UpbitClient()
    try:
        yield client
    finally:
        await client.aclose()


def clear_coins_cache() -> None:
    """테스트 격리용 캐시 초기화."""
    global _coins_cache  # noqa: PLW0603
    _coins_cache = None


@router.get("/api/markets/coins", response_model=list[CoinMarket])
async def list_coin_markets(
    client: UpbitClient = Depends(get_upbit_client),  # noqa: B008
) -> list[CoinMarket]:
    """업비트 KRW 마켓 목록 (1시간 캐시)."""
    global _coins_cache  # noqa: PLW0603
    now = datetime.now(tz=_KST)
    if _coins_cache is not None and now < _coins_cache[0]:
        return _coins_cache[1]

    raw = await client.list_krw_markets_detailed()
    coins = [CoinMarket(market=item["market"], korean_name=item["korean_name"]) for item in raw]
    _coins_cache = (now + _COINS_CACHE_TTL, coins)
    return coins


@router.get("/api/markets/kr", response_model=list[KrUniverseStock])
async def list_kr_universe() -> list[KrUniverseStock]:
    """국장 큐레이션 유니버스 (정적 43종, 섹터 포함)."""
    return [
        KrUniverseStock(code=s.code, name=s.name, market=s.market, sector=s.sector)
        for s in KR_UNIVERSE
    ]
