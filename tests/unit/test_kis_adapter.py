"""KisApiAdapter 유닛 테스트.

네트워크 없이 실행 가능한 테스트만 포함한다.
- _resample_to_120m: 순수 함수 — mock 불필요
- _parse_candles: 순수 함수 — mock 불필요
- _ensure_token: httpx mock 사용
- fetch_candles (HOUR_2): _fetch_60m_candles 가 mock 반환값을 받아 집계하는지 확인
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from signal_program.enums import Timeframe
from signal_program.exchanges.kis_api import KisApiAdapter
from signal_program.models import Candle

KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------ #
# 픽스처 헬퍼
# ------------------------------------------------------------------ #


def _make_candle(
    symbol: str,
    dt: datetime,
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
    volume: float = 1000.0,
    quote_volume: float = 100_000.0,
) -> Candle:
    return Candle(
        market=symbol,
        opened_at=dt,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        quote_volume=quote_volume,
    )


def _make_adapter(is_paper: bool = True) -> KisApiAdapter:
    return KisApiAdapter(
        app_key="test_key",
        app_secret="test_secret",
        is_paper=is_paper,
    )


# ------------------------------------------------------------------ #
# _resample_to_120m — 순수 함수 테스트
# ------------------------------------------------------------------ #


class TestResampleTo120m:
    """ADR-0016 _resample_to_120m 알고리즘 검증."""

    def _base_dt(self, hour: int) -> datetime:
        return datetime(2026, 5, 26, hour, 0, tzinfo=KST)

    def test_empty_input_returns_empty(self) -> None:
        result = KisApiAdapter._resample_to_120m([], target_count=5)
        assert result == []

    def test_single_candle_returns_empty(self) -> None:
        """캔들 1개는 쌍을 이룰 수 없으므로 빈 결과."""
        c = _make_candle("005930", self._base_dt(9))
        result = KisApiAdapter._resample_to_120m([c], target_count=5)
        assert result == []

    def test_two_candles_makes_one_120m(self) -> None:
        c1 = _make_candle("005930", self._base_dt(9), open_=100, high=120, low=90, close=110, volume=500, quote_volume=50_000)
        c2 = _make_candle("005930", self._base_dt(10), open_=110, high=130, low=95, close=125, volume=600, quote_volume=60_000)

        result = KisApiAdapter._resample_to_120m([c1, c2], target_count=5)

        assert len(result) == 1
        r = result[0]
        assert r.market == "005930"
        assert r.opened_at == self._base_dt(9)   # c1.opened_at
        assert r.open == 100.0                     # c1.open
        assert r.high == 130.0                     # max(120, 130)
        assert r.low == 90.0                       # min(90, 95)
        assert r.close == 125.0                    # c2.close
        assert r.volume == 1100.0                  # 500 + 600
        assert r.quote_volume == 110_000.0         # 50_000 + 60_000

    def test_four_candles_makes_two_120m(self) -> None:
        candles = [
            _make_candle("005930", self._base_dt(h), open_=h * 10, high=h * 11, low=h * 9, close=h * 10 + 5, volume=100.0, quote_volume=1000.0)
            for h in [9, 10, 11, 12]
        ]

        result = KisApiAdapter._resample_to_120m(candles, target_count=5)

        assert len(result) == 2
        # 첫 번째 120m 캔들: 09~10봉 집계
        assert result[0].opened_at == self._base_dt(9)
        assert result[0].open == 90.0   # candles[0].open = 9 * 10
        assert result[0].close == 105.0  # candles[1].close = 10 * 10 + 5
        # 두 번째 120m 캔들: 11~12봉 집계
        assert result[1].opened_at == self._base_dt(11)

    def test_odd_candles_ignores_last(self) -> None:
        """홀수 개 캔들 → 마지막 캔들은 쌍을 이루지 못해 무시된다."""
        candles = [
            _make_candle("005930", self._base_dt(h))
            for h in [9, 10, 11]
        ]
        result = KisApiAdapter._resample_to_120m(candles, target_count=5)
        assert len(result) == 1  # (9,10) 쌍만 집계; 11은 버려짐

    def test_target_count_limits_output(self) -> None:
        """target_count보다 많이 생성되면 최신 N개만 반환한다."""
        candles = [
            _make_candle("005930", self._base_dt(h))
            for h in [9, 10, 11, 12, 13, 14]
        ]
        result = KisApiAdapter._resample_to_120m(candles, target_count=2)
        assert len(result) == 2
        # 가장 최신 2개: (11,12) 쌍과 (13,14) 쌍
        assert result[0].opened_at == self._base_dt(11)
        assert result[1].opened_at == self._base_dt(13)

    def test_high_is_max_of_pair(self) -> None:
        c1 = _make_candle("005930", self._base_dt(9), high=200)
        c2 = _make_candle("005930", self._base_dt(10), high=150)
        result = KisApiAdapter._resample_to_120m([c1, c2], target_count=5)
        assert result[0].high == 200.0

    def test_low_is_min_of_pair(self) -> None:
        c1 = _make_candle("005930", self._base_dt(9), low=80)
        c2 = _make_candle("005930", self._base_dt(10), low=70)
        result = KisApiAdapter._resample_to_120m([c1, c2], target_count=5)
        assert result[0].low == 70.0


# ------------------------------------------------------------------ #
# _parse_candles — 순수 함수 테스트
# ------------------------------------------------------------------ #


class TestParseCandles:
    def _make_output2_item(
        self,
        date: str = "20260526",
        time: str = "090000",
        oprc: str = "70000",
        hgpr: str = "71000",
        lwpr: str = "69000",
        prpr: str = "70500",
        vol: str = "1000",
        pbmn: str = "70000000",
    ) -> dict:
        return {
            "stck_bsop_date": date,
            "stck_cntg_hour": time,
            "stck_oprc": oprc,
            "stck_hgpr": hgpr,
            "stck_lwpr": lwpr,
            "stck_prpr": prpr,
            "cntg_vol": vol,
            "acml_tr_pbmn": pbmn,
        }

    def test_valid_item_parsed_correctly(self) -> None:
        item = self._make_output2_item()
        candles = KisApiAdapter._parse_candles("005930", [item])

        assert len(candles) == 1
        c = candles[0]
        assert c.market == "005930"
        assert c.opened_at == datetime(2026, 5, 26, 9, 0, 0, tzinfo=KST)
        assert c.open == 70000.0
        assert c.high == 71000.0
        assert c.low == 69000.0
        assert c.close == 70500.0
        assert c.volume == 1000.0
        assert c.quote_volume == 70_000_000.0

    def test_empty_date_skipped(self) -> None:
        item = self._make_output2_item(date="", time="090000")
        candles = KisApiAdapter._parse_candles("005930", [item])
        assert candles == []

    def test_empty_time_skipped(self) -> None:
        item = self._make_output2_item(date="20260526", time="")
        candles = KisApiAdapter._parse_candles("005930", [item])
        assert candles == []

    def test_invalid_number_skipped(self) -> None:
        item = self._make_output2_item(oprc="INVALID")
        candles = KisApiAdapter._parse_candles("005930", [item])
        assert candles == []

    def test_multiple_items(self) -> None:
        items = [
            self._make_output2_item(time="150000"),
            self._make_output2_item(time="140000"),
        ]
        candles = KisApiAdapter._parse_candles("005930", items)
        assert len(candles) == 2

    def test_candle_timezone_is_kst(self) -> None:
        item = self._make_output2_item()
        candles = KisApiAdapter._parse_candles("005930", [item])
        assert candles[0].opened_at.tzinfo == KST


# ------------------------------------------------------------------ #
# _ensure_token — httpx mock 테스트
# ------------------------------------------------------------------ #


class TestEnsureToken:
    async def test_issues_new_token_when_empty(self) -> None:
        adapter = _make_adapter()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "tok_abc123",
            "token_type": "Bearer",
            "expires_in": 86400,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, "post", new=AsyncMock(return_value=mock_response)):
            token = await adapter._ensure_token()

        assert token == "tok_abc123"
        assert adapter._token == "tok_abc123"
        assert adapter._token_expires_at is not None

    async def test_reuses_valid_token(self) -> None:
        adapter = _make_adapter()
        adapter._token = "existing_token"
        adapter._token_expires_at = datetime.now(tz=UTC) + timedelta(hours=12)

        with patch.object(adapter._client, "post", new=AsyncMock()) as mock_post:
            token = await adapter._ensure_token()

        assert token == "existing_token"
        mock_post.assert_not_called()

    async def test_refreshes_token_near_expiry(self) -> None:
        adapter = _make_adapter()
        adapter._token = "old_token"
        # 만료 5분 전 → _TOKEN_REFRESH_MARGIN(10분) 이내이므로 재발급 필요
        adapter._token_expires_at = datetime.now(tz=UTC) + timedelta(minutes=5)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new_token",
            "token_type": "Bearer",
            "expires_in": 86400,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, "post", new=AsyncMock(return_value=mock_response)):
            token = await adapter._ensure_token()

        assert token == "new_token"

    async def test_does_not_refresh_token_outside_margin(self) -> None:
        adapter = _make_adapter()
        adapter._token = "fresh_token"
        # 만료 11분 후 → _TOKEN_REFRESH_MARGIN(10분) 밖이므로 재발급 불필요
        adapter._token_expires_at = datetime.now(tz=UTC) + timedelta(minutes=11)

        with patch.object(adapter._client, "post", new=AsyncMock()) as mock_post:
            token = await adapter._ensure_token()

        assert token == "fresh_token"
        mock_post.assert_not_called()


# ------------------------------------------------------------------ #
# fetch_candles(HOUR_2) — 120분봉 집계 통합
# ------------------------------------------------------------------ #


class TestFetchCandles120m:
    """HOUR_2 경로: _fetch_60m_candles 결과를 _resample_to_120m으로 집계하는지 확인."""

    async def test_hour2_aggregates_60m_candles(self) -> None:
        adapter = _make_adapter()

        # 60분봉 4개(2쌍) mock
        base = datetime(2026, 5, 26, 9, 0, tzinfo=KST)
        mock_60m = [
            _make_candle("005930", base + timedelta(hours=h))
            for h in range(4)
        ]

        with patch.object(
            adapter, "_fetch_60m_candles", new=AsyncMock(return_value=mock_60m)
        ):
            result = await adapter.fetch_candles("005930", Timeframe.HOUR_2, count=2)

        # 4개 60m → 2개 120m
        assert len(result) == 2

    async def test_hour2_requests_double_count_of_60m(self) -> None:
        """HOUR_2 count=3이면 _fetch_60m_candles가 count=6으로 호출되어야 한다."""
        adapter = _make_adapter()

        with patch.object(
            adapter, "_fetch_60m_candles", new=AsyncMock(return_value=[])
        ) as mock_fetch:
            await adapter.fetch_candles("005930", Timeframe.HOUR_2, count=3)

        mock_fetch.assert_called_once()
        _, kwargs = mock_fetch.call_args
        assert kwargs.get("count") == 6 or mock_fetch.call_args.args[1] == 6

    async def test_hour1_calls_60m_directly(self) -> None:
        adapter = _make_adapter()

        base = datetime(2026, 5, 26, 9, 0, tzinfo=KST)
        mock_60m = [_make_candle("005930", base + timedelta(hours=h)) for h in range(3)]

        with patch.object(
            adapter, "_fetch_60m_candles", new=AsyncMock(return_value=mock_60m)
        ) as mock_fetch:
            result = await adapter.fetch_candles("005930", Timeframe.HOUR_1, count=3)

        mock_fetch.assert_called_once()
        assert len(result) == 3


# ------------------------------------------------------------------ #
# config 통합 — KIS 필드
# ------------------------------------------------------------------ #


class TestConfigKisFields:
    """Settings에 KIS 필드가 올바르게 추가됐는지 확인한다."""

    def test_defaults(self) -> None:
        from signal_program.config import Settings

        s = Settings(whitelist_markets=["KRW-BTC"])
        assert s.kis_app_key == ""
        assert s.kis_app_secret == ""
        assert s.kis_is_paper is True
        assert s.kr_enabled is False
        assert s.kr_whitelist_symbols == []
        assert s.kr_cooldown_hours_60m == 2
        assert s.kr_cooldown_hours_120m == 4

    def test_kr_whitelist_symbols_from_comma_string(self) -> None:
        from signal_program.config import Settings

        s = Settings(
            whitelist_markets=["KRW-BTC"],
            kr_whitelist_symbols="005930,000660,035420",  # type: ignore[arg-type]
        )
        assert s.kr_whitelist_symbols == ["005930", "000660", "035420"]

    def test_kr_whitelist_symbols_from_list(self) -> None:
        from signal_program.config import Settings

        s = Settings(
            whitelist_markets=["KRW-BTC"],
            kr_whitelist_symbols=["005930", "000660"],
        )
        assert s.kr_whitelist_symbols == ["005930", "000660"]


# ------------------------------------------------------------------ #
# enums — HOUR_2 + KrMarket
# ------------------------------------------------------------------ #


class TestNewEnums:
    def test_hour2_value(self) -> None:
        assert Timeframe.HOUR_2 == "120"

    def test_hour1_unchanged(self) -> None:
        assert Timeframe.HOUR_1 == "60"

    def test_kr_market_values(self) -> None:
        from signal_program.enums import KrMarket

        assert KrMarket.KOSPI == "KOSPI"
        assert KrMarket.KOSDAQ == "KOSDAQ"
