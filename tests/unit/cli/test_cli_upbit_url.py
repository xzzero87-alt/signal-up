"""cli.py — _run_live_coro / _run_async의 httpx.AsyncClient에 base_url이 있는지 회귀 테스트.

결함 (v2.0.0): _run_live_coro와 _run_async가 httpx.AsyncClient(timeout=10.0)에
base_url 없이 UpbitClient에 전달 → "/v1/candles/..." 상대 경로 요청 →
"Request URL is missing 'http://' or 'https://' protocol" 에러 → 19/19 마켓 실패.
"""

from __future__ import annotations

import pathlib
import re

import httpx
import pytest


def _cli_source() -> str:
    return (pathlib.Path(__file__).parents[3] / "src" / "signal_program" / "cli.py").read_text(
        encoding="utf-8"
    )


def _extract_func(text: str, name: str) -> str:
    """함수 이름으로 시작하는 블록을 추출 (다음 def/async def까지)."""
    start = text.find(f"async def {name}")
    if start == -1:
        start = text.find(f"def {name}")
    assert start != -1, f"{name} 함수를 cli.py에서 찾을 수 없음"
    rest = text[start + len(name):]
    # 다음 최상위 함수 정의 위치
    nxt = re.search(r"\n(def |async def )", rest)
    return rest[: nxt.start()] if nxt else rest


def test_run_live_coro_httpx_client_has_base_url() -> None:
    """결함 회귀: _run_live_coro의 httpx.AsyncClient에 base_url이 있어야 한다."""
    func = _extract_func(_cli_source(), "_run_live_coro")
    assert re.search(r"AsyncClient\s*\([^)]*base_url", func, re.DOTALL), (
        "_run_live_coro: httpx.AsyncClient에 base_url 없음 → "
        "UpbitClient가 /v1/... 상대 경로를 요청하여 19/19 마켓 실패"
    )


def test_run_async_httpx_client_has_base_url() -> None:
    """결함 회귀: _run_async의 httpx.AsyncClient에 base_url이 있어야 한다."""
    func = _extract_func(_cli_source(), "_run_async")
    assert re.search(r"AsyncClient\s*\([^)]*base_url", func, re.DOTALL), (
        "_run_async: httpx.AsyncClient에 base_url 없음 → "
        "signal run 커맨드에서도 동일 URL 결함"
    )


@pytest.mark.anyio
async def test_upbit_client_without_base_url_raises_protocol_error() -> None:
    """결함 재현: base_url 없는 AsyncClient → UnsupportedProtocol — v2.0.0 실패 원인."""
    from signal_program.enums import Timeframe
    from signal_program.exchanges.upbit import UpbitClient

    async with httpx.AsyncClient(timeout=1.0) as broken_http:  # base_url 없음
        client = UpbitClient(_client=broken_http)
        with pytest.raises((httpx.UnsupportedProtocol, httpx.InvalidURL)):
            await client.fetch_candles("KRW-BTC", Timeframe.HOUR_1, 1)


@pytest.mark.anyio
async def test_upbit_client_with_base_url_sends_full_https_url() -> None:
    """base_url 있는 AsyncClient → https://api.upbit.com으로 시작하는 URL 요청."""
    import json as _json

    from signal_program.enums import Timeframe
    from signal_program.exchanges.upbit import UpbitClient

    sent_url: list[str] = []

    class _CaptureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            sent_url.append(str(request.url))
            candle = {
                "market": "KRW-BTC",
                "candle_date_time_kst": "2026-01-01T14:00:00",
                "opening_price": 100.0,
                "high_price": 110.0,
                "low_price": 90.0,
                "trade_price": 105.0,
                "candle_acc_trade_volume": 10.0,
                "candle_acc_trade_price": 1050.0,
            }
            return httpx.Response(200, content=_json.dumps([candle]).encode())

    async with httpx.AsyncClient(
        base_url="https://api.upbit.com",
        transport=_CaptureTransport(),
        timeout=5.0,
    ) as http:
        client = UpbitClient(_client=http)
        candles = await client.fetch_candles("KRW-BTC", Timeframe.HOUR_1, 1)

    assert len(candles) == 1
    assert sent_url, "요청이 전송되지 않았음"
    assert sent_url[0].startswith("https://api.upbit.com"), (
        f"URL이 https://api.upbit.com으로 시작해야 함, 실제: {sent_url[0]}"
    )
