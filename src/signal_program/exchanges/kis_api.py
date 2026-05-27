"""KIS Open API (한국투자증권) 어댑터 — HOUR_1 (60분봉) + HOUR_2 (120분봉 집계).

ADR-0016: https://github.com/… (로컬 docs/adr/0016-kis-api-korean-stock-datasource.md)

인증: OAuth2 액세스 토큰 (24h TTL), 만료 10분 전 자동 재발급.
Rate limit: asyncio.Semaphore(5) — KIS 초당 20건 제한 대응.
HOUR_2: KIS 미지원 → 60분봉 2개씩 페어링 후 집계 (_resample_to_120m).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx

from signal_program.enums import Timeframe
from signal_program.models import Candle

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
UTC = UTC

_REAL_BASE = "https://openapi.koreainvestment.com:9443"
_PAPER_BASE = "https://openapivts.koreainvestment.com:9443"
_TOKEN_PATH = "/oauth2/tokenP"
_MINUTE_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
_TR_ID = "FHKST03010200"
_MKT_DIV_CODE = "J"  # 주식 시장 구분 코드 (코스피/코스닥 공통)
_MAX_CANDLES_PER_CALL = 30  # KIS API 단일 호출 최대 반환 캔들 수
_MAX_PAGINATION_CALLS = 5  # 최대 페이지네이션 횟수 (5 × 30 = 150 candles)
_TOKEN_REFRESH_MARGIN = timedelta(minutes=10)  # 만료 N분 전 선제 재발급


class KoreanStockExchange(Protocol):
    """국내 주식 거래소 어댑터 Protocol.

    암호화폐 Exchange Protocol과 별도로 정의하여
    기존 Upbit 코드에 영향 없이 독립 교체가 가능하다.
    """

    async def list_symbols(self) -> list[str]: ...

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
        to: datetime | None = None,
    ) -> list[Candle]: ...


class KisApiAdapter:
    """KIS Open API 기반 국내 주식 캔들 어댑터.

    인스턴스는 httpx.AsyncClient를 보유하므로, 사용이 끝나면 aclose()를 호출하거나
    async with KisApiAdapter(...) as adapter: 패턴으로 사용한다.
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        is_paper: bool = True,
        semaphore_count: int = 5,
        http_timeout: float = 30.0,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = _PAPER_BASE if is_paper else _REAL_BASE
        self._semaphore = asyncio.Semaphore(semaphore_count)
        self._token_lock = asyncio.Lock()
        self._token: str = ""
        self._token_expires_at: datetime | None = None
        self._client = httpx.AsyncClient(timeout=http_timeout)

    # ------------------------------------------------------------------ #
    # Protocol 구현
    # ------------------------------------------------------------------ #

    async def list_symbols(self) -> list[str]:
        """심볼 목록을 반환한다.

        어댑터는 심볼 목록을 관리하지 않는다.
        호출자(KrStockRunnerService)가 config.kr_whitelist_symbols를 사용한다.
        """
        return []

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
        to: datetime | None = None,
    ) -> list[Candle]:
        """60분봉 또는 120분봉 캔들을 반환한다.

        HOUR_2(120분봉)는 KIS 미지원이므로 60분봉 2배를 가져와 집계한다.

        Args:
            symbol: 종목코드 (예: "005930")
            timeframe: HOUR_1(60분) 또는 HOUR_2(120분)
            count: 필요한 캔들 수
            to: 이 시각 이전 캔들을 반환 (None이면 현재 시각)

        Returns:
            oldest → newest 정렬된 Candle 목록 (count개 이하)
        """
        if timeframe == Timeframe.HOUR_2:
            # 120분봉: 60분봉을 2배 수집 후 집계
            raw = await self._fetch_60m_candles(symbol, count=count * 2, to=to)
            return self._resample_to_120m(raw, target_count=count)
        return await self._fetch_60m_candles(symbol, count=count, to=to)

    # ------------------------------------------------------------------ #
    # 토큰 관리
    # ------------------------------------------------------------------ #

    async def _ensure_token(self) -> str:
        """유효한 액세스 토큰을 반환한다.

        토큰이 없거나 만료 10분 전이면 KIS에 재발급 요청한다.
        동시성 안전을 위해 asyncio.Lock으로 직렬화한다.
        """
        async with self._token_lock:
            now = datetime.now(tz=UTC)
            if (
                self._token
                and self._token_expires_at is not None
                and now < self._token_expires_at - _TOKEN_REFRESH_MARGIN
            ):
                return self._token

            try:
                resp = await self._client.post(
                    f"{self._base_url}{_TOKEN_PATH}",
                    json={
                        "grant_type": "client_credentials",
                        "appkey": self._app_key,
                        "appsecret": self._app_secret,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self._token = data["access_token"]
                expires_in: int = int(data.get("expires_in", 86400))
                self._token_expires_at = now + timedelta(seconds=expires_in)
                logger.info("kis_token_issued", extra={"expires_in_seconds": expires_in})
            except (httpx.HTTPStatusError, httpx.RequestError, KeyError) as exc:
                logger.error("kis_token_refresh_failed", extra={"error": str(exc)})
                raise

            return self._token

    # ------------------------------------------------------------------ #
    # 60분봉 수집 (페이지네이션)
    # ------------------------------------------------------------------ #

    async def _fetch_60m_candles(
        self,
        symbol: str,
        count: int,
        to: datetime | None = None,
    ) -> list[Candle]:
        """KIS API에서 60분봉을 페이지네이션으로 수집한다.

        단일 호출당 최대 30개를 반환하므로, count에 도달할 때까지 반복 호출한다.
        최대 _MAX_PAGINATION_CALLS(5)회 호출 = 최대 150 candles.

        Args:
            symbol: 종목코드
            count: 목표 캔들 수
            to: 이 시각 이전 데이터 요청 (None이면 현재 KST)

        Returns:
            oldest → newest 정렬, 중복 제거된 Candle 목록 (count개 이하)
        """
        cursor: datetime = (to or datetime.now(tz=KST)).astimezone(KST)
        accumulated: list[Candle] = []

        async with self._semaphore:
            token = await self._ensure_token()

            for _ in range(_MAX_PAGINATION_CALLS):
                batch = await self._call_minute_chart(symbol, cursor, token)
                if not batch:
                    break

                accumulated.extend(batch)

                if len(accumulated) >= count:
                    break

                # 다음 페이지: 가장 오래된 캔들 1분 전으로 커서 이동
                oldest_in_batch = min(batch, key=lambda c: c.opened_at)
                cursor = oldest_in_batch.opened_at - timedelta(minutes=1)

        # 정렬 + 중복 제거 (시각 기준)
        accumulated.sort(key=lambda c: c.opened_at)
        seen_times: set[datetime] = set()
        deduped: list[Candle] = []
        for candle in accumulated:
            if candle.opened_at not in seen_times:
                seen_times.add(candle.opened_at)
                deduped.append(candle)

        return deduped[-count:]

    # ------------------------------------------------------------------ #
    # KIS API 단일 호출
    # ------------------------------------------------------------------ #

    async def _call_minute_chart(
        self,
        symbol: str,
        to: datetime,
        token: str,
    ) -> list[Candle]:
        """KIS 분봉 차트 단일 호출 → Candle 목록 반환 (newest → oldest).

        Args:
            symbol: 종목코드
            to: 이 시각 이전 캔들을 요청 (KST)
            token: 유효한 액세스 토큰

        Returns:
            Candle 목록. API 오류 시 빈 리스트.
        """
        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": _MKT_DIV_CODE,
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_HOUR_1": to.strftime("%H%M%S"),
            "FID_PW_DATA_INCU_YN": "Y",  # 전일 데이터 포함
        }
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": _TR_ID,
            "custtype": "P",
        }

        try:
            resp = await self._client.get(
                f"{self._base_url}{_MINUTE_CHART_PATH}",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(
                "kis_chart_request_failed",
                extra={"symbol": symbol, "error": str(exc)},
            )
            return []

        data = resp.json()

        # KIS API 비즈니스 에러 확인 (rt_cd != "0")
        if data.get("rt_cd") != "0":
            logger.warning(
                "kis_chart_api_error",
                extra={
                    "symbol": symbol,
                    "rt_cd": data.get("rt_cd"),
                    "msg": data.get("msg1"),
                },
            )
            return []

        output2: list[dict] = data.get("output2") or []
        return self._parse_candles(symbol, output2)

    # ------------------------------------------------------------------ #
    # 파싱 헬퍼
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_candles(symbol: str, output2: list[dict]) -> list[Candle]:
        """KIS output2 항목 목록을 Candle 목록으로 변환한다.

        KIS는 데이터를 newest → oldest 순서로 반환한다.
        잘못된 항목은 WARNING 로그 후 건너뛴다.
        """
        candles: list[Candle] = []
        for item in output2:
            try:
                date_str = item.get("stck_bsop_date", "")  # "YYYYMMDD"
                time_str = item.get("stck_cntg_hour", "")  # "HHMMSS"
                if len(date_str) != 8 or len(time_str) != 6:
                    continue

                opened_at = datetime(
                    int(date_str[:4]),
                    int(date_str[4:6]),
                    int(date_str[6:8]),
                    int(time_str[:2]),
                    int(time_str[2:4]),
                    int(time_str[4:6]),
                    tzinfo=KST,
                )
                candles.append(
                    Candle(
                        market=symbol,
                        opened_at=opened_at,
                        open=float(item["stck_oprc"]),
                        high=float(item["stck_hgpr"]),
                        low=float(item["stck_lwpr"]),
                        close=float(item["stck_prpr"]),
                        volume=float(item["cntg_vol"]),
                        quote_volume=float(item["acml_tr_pbmn"]),
                    )
                )
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "kis_candle_parse_error",
                    extra={"symbol": symbol, "item": item, "error": str(exc)},
                )

        return candles

    # ------------------------------------------------------------------ #
    # 120분봉 집계 (ADR-0016)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resample_to_120m(candles: list[Candle], target_count: int) -> list[Candle]:
        """60분봉 2개를 묶어 120분봉으로 집계한다 (ADR-0016).

        입력 candles는 oldest → newest 정렬을 가정한다.
        인덱스 0부터 2개씩 페어링: c1(짝수), c2(홀수).
        c1.opened_at이 120분봉의 시작 시각.

        Args:
            candles: oldest → newest 정렬된 60분봉 목록
            target_count: 반환할 최대 120분봉 수

        Returns:
            oldest → newest 정렬된 120분봉 목록 (target_count개 이하)
        """
        result: list[Candle] = []
        for i in range(0, len(candles) - 1, 2):
            c1, c2 = candles[i], candles[i + 1]
            result.append(
                Candle(
                    market=c1.market,
                    opened_at=c1.opened_at,
                    open=c1.open,
                    high=max(c1.high, c2.high),
                    low=min(c1.low, c2.low),
                    close=c2.close,
                    volume=c1.volume + c2.volume,
                    quote_volume=c1.quote_volume + c2.quote_volume,
                )
            )
        return result[-target_count:]

    # ------------------------------------------------------------------ #
    # 컨텍스트 매니저 지원
    # ------------------------------------------------------------------ #

    async def aclose(self) -> None:
        """httpx 클라이언트를 닫는다."""
        await self._client.aclose()

    async def __aenter__(self) -> KisApiAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
