"""TelegramNotifier — TDD RED → GREEN 시나리오 8종."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import httpx
import pytest
import structlog.testing
from pydantic import SecretStr

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import IndicatorSnapshot, Signal
from signal_program.notifiers.telegram import TelegramNotifier

KST = ZoneInfo("Asia/Seoul")
pytestmark = pytest.mark.anyio

FAKE_TOKEN = SecretStr("123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
CHAT_ID = "987654321"
_OK_BODY = {"ok": True, "result": {"message_id": 1}}
_ERR_401 = {"ok": False, "error_code": 401, "description": "Unauthorized"}
_ERR_500 = {"ok": False, "error_code": 500, "description": "Internal Server Error"}


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def signal() -> Signal:
    return Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=92_000_000.0,
        triggered_at=datetime(2026, 5, 12, 14, 0, tzinfo=KST),
        indicators=IndicatorSnapshot(
            bb_upper=95_000_000.0,
            bb_middle=91_000_000.0,
            bb_lower=87_000_000.0,
            bb_width=0.088,
            bb_pct_b=0.25,
            cci=-150.0,
            volume_ratio=1.3,
            bb_width_quantile=None,
        ),
    )


class _AsyncMockTransport(httpx.AsyncBaseTransport):
    """asyncio 호환 MockTransport."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self._handler = handler
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


def make_transport(status: int, body: dict) -> _AsyncMockTransport:
    return _AsyncMockTransport(lambda _: httpx.Response(status, json=body))


def make_notifier(transport: _AsyncMockTransport, **kwargs) -> TelegramNotifier:
    client = httpx.AsyncClient(transport=transport)
    return TelegramNotifier(
        bot_token=FAKE_TOKEN,
        chat_id=CHAT_ID,
        http_client=client,
        _retry_wait_multiplier=0.0,
        **kwargs,
    )


# ── 시나리오 8종 ──────────────────────────────────────────────────────────────

# (a) 정상 전송 200 — 1회 호출, chat_id·text 포함
async def test_a_ok_sends_once(signal: Signal) -> None:
    tr = make_transport(200, _OK_BODY)
    notifier = make_notifier(tr)
    await notifier.send_signal(signal, chart_path=None)
    assert len(tr.requests) == 1
    body = tr.requests[0].content.decode()
    assert CHAT_ID in body
    assert "KRW-BTC" in body


# (b) 메시지 포맷 — DESIGN §5.3 필수 필드
async def test_b_message_format(signal: Signal) -> None:
    tr = make_transport(200, _OK_BODY)
    notifier = make_notifier(tr)
    await notifier.send_signal(signal, chart_path=None)
    text = tr.requests[0].content.decode()
    assert "92,000,000" in text   # 가격 콤마
    assert "σ" in text            # BB %B
    assert "CCI" in text          # CCI
    assert "거래량" in text        # 거래량
    assert "KST" in text          # 시각
    assert "참고용 시그널" in text  # 고지
    assert "차트 첨부" in text     # M8 예정


# (c) 401 → 재시도 없이 1회만
async def test_c_401_no_retry(signal: Signal) -> None:
    tr = make_transport(401, _ERR_401)
    notifier = make_notifier(tr, max_retries=3)
    await notifier.send_signal(signal, chart_path=None)
    assert len(tr.requests) == 1


# (d) 5xx → max_retries=3회 후 실패, 예외 없음
async def test_d_5xx_retries_exhausted(signal: Signal) -> None:
    tr = make_transport(503, _ERR_500)
    notifier = make_notifier(tr, max_retries=3)
    await notifier.send_signal(signal, chart_path=None)
    assert len(tr.requests) == 3


# (e) NetworkError → 3회 재시도
async def test_e_network_error_retries(signal: Signal) -> None:
    def err_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.NetworkError("Connection refused")

    tr = _AsyncMockTransport(err_handler)
    notifier = make_notifier(tr, max_retries=3)
    await notifier.send_signal(signal, chart_path=None)
    assert len(tr.requests) == 3


# (f) TimeoutException → 재시도
async def test_f_timeout_retries(signal: Signal) -> None:
    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Timeout")

    tr = _AsyncMockTransport(timeout_handler)
    notifier = make_notifier(tr, max_retries=3)
    await notifier.send_signal(signal, chart_path=None)
    assert len(tr.requests) == 3


# (g) dry_run=True → HTTP 호출 0회
async def test_g_dry_run_no_http(signal: Signal) -> None:
    tr = make_transport(200, _OK_BODY)
    notifier = make_notifier(tr, dry_run=True)
    await notifier.send_signal(signal, chart_path=None)
    assert len(tr.requests) == 0


# (h) 토큰 마스킹 — 로그 어디에도 평문 토큰 미노출
async def test_h_token_not_in_logs(signal: Signal) -> None:
    plain_token = FAKE_TOKEN.get_secret_value()
    token_pattern = re.compile(r"\d{5,}:[A-Za-z0-9_\-]{10,}")

    with structlog.testing.capture_logs() as cap:
        tr = make_transport(401, _ERR_401)
        notifier = make_notifier(tr)
        await notifier.send_signal(signal, chart_path=None)

    log_str = str(cap)
    assert plain_token not in log_str
    assert not token_pattern.findall(log_str)
