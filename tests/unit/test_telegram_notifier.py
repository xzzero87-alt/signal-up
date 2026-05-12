"""TelegramNotifier — TDD RED → GREEN 시나리오 8종 + Phase 3 포맷·경계 보강."""
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
from hypothesis import given, settings
from hypothesis import strategies as st

from signal_program.notifiers.telegram import TelegramNotifier, format_message

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
        await request.aread()  # streaming body (multipart 등) 읽기 완료
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


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — 포맷·경계 보강
# ═══════════════════════════════════════════════════════════════════════════════

def _make_signal(
    direction: SignalDirection,
    strength: SignalStrength,
    mode: StrategyMode,
    price: float = 50_000_000.0,
) -> Signal:
    return Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=mode,
        direction=direction,
        strength=strength,
        price=price,
        triggered_at=datetime(2026, 5, 12, 15, 0, tzinfo=KST),
        indicators=IndicatorSnapshot(
            bb_upper=52_000_000.0,
            bb_middle=50_000_000.0,
            bb_lower=48_000_000.0,
            bb_width=0.04,
            bb_pct_b=0.5,
            cci=130.0,
            volume_ratio=1.8,
            bb_width_quantile=None,
        ),
    )


# format_message 8조합 parametrize
@pytest.mark.parametrize(
    "direction,strength,mode,expected_emoji,expected_mode_label",
    [
        (SignalDirection.BUY, SignalStrength.NORMAL, StrategyMode.MEAN_REVERSION, "🟢", "평균회귀"),
        (SignalDirection.BUY, SignalStrength.STRONG, StrategyMode.MEAN_REVERSION, "🟢🟢", "평균회귀"),
        (SignalDirection.SELL, SignalStrength.NORMAL, StrategyMode.MEAN_REVERSION, "🔴", "평균회귀"),
        (SignalDirection.SELL, SignalStrength.STRONG, StrategyMode.MEAN_REVERSION, "🔴🔴", "평균회귀"),
        (SignalDirection.BUY, SignalStrength.NORMAL, StrategyMode.SQUEEZE_BREAKOUT, "🟢", "스퀴즈 돌파"),
        (SignalDirection.BUY, SignalStrength.STRONG, StrategyMode.SQUEEZE_BREAKOUT, "🟢🟢", "스퀴즈 돌파"),
        (SignalDirection.SELL, SignalStrength.NORMAL, StrategyMode.SQUEEZE_BREAKOUT, "🔴", "스퀴즈 돌파"),
        (SignalDirection.SELL, SignalStrength.STRONG, StrategyMode.SQUEEZE_BREAKOUT, "🔴🔴", "스퀴즈 돌파"),
    ],
)
def test_format_message_8_combinations(
    direction: SignalDirection,
    strength: SignalStrength,
    mode: StrategyMode,
    expected_emoji: str,
    expected_mode_label: str,
) -> None:
    """direction × strength × mode 8조합 — emoji·모드 라벨·필수 필드 검증."""
    sig = _make_signal(direction, strength, mode)
    text = format_message(sig)
    assert expected_emoji in text
    assert expected_mode_label in text
    assert "KRW-BTC" in text
    assert "CCI" in text
    assert "KST" in text
    assert "참고용 시그널" in text


# chat_id 형식 다양성
@pytest.mark.parametrize("chat_id", ["987654321", "-1001234567890", "@my_channel"])
async def test_chat_id_formats(signal: Signal, chat_id: str) -> None:
    """개인(양수), 그룹(음수), 채널(@) chat_id 모두 payload에 포함."""
    tr = make_transport(200, _OK_BODY)
    client = httpx.AsyncClient(transport=tr)
    notifier = TelegramNotifier(
        bot_token=FAKE_TOKEN,
        chat_id=chat_id,
        http_client=client,
        _retry_wait_multiplier=0.0,
    )
    await notifier.send_signal(signal, chart_path=None)
    body = tr.requests[0].content.decode()
    assert chat_id in body


# 메시지 4096자 한도 — 잘림 처리
def test_message_truncation() -> None:
    """format_message가 4096자를 초과하면 '...'으로 잘린다."""
    from signal_program.notifiers.telegram import _MAX_TEXT_LEN

    sig = _make_signal(SignalDirection.BUY, SignalStrength.NORMAL, StrategyMode.MEAN_REVERSION)
    # 가격을 엄청 큰 수로 만들어 문자열을 늘림
    long_sig = Signal(
        **{**sig.model_dump(), "market": "KRW-" + "X" * 4100, "price": 1.0},
    )
    text = format_message(long_sig)
    assert len(text) <= _MAX_TEXT_LEN
    assert text.endswith("...")


# Hypothesis: 임의 Signal → format_message가 non-empty str 반환, 토큰 미포함
@given(
    price=st.floats(min_value=1.0, max_value=1e12, allow_nan=False, allow_infinity=False),
    cci=st.floats(min_value=-2000.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    vr=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=1000)
def test_hypothesis_format_message_no_exception(
    price: float, cci: float, vr: float
) -> None:
    """임의 Signal 값 → format_message 예외 없이 non-empty 반환."""
    sig = Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=price,
        triggered_at=datetime(2026, 5, 12, 14, 0, tzinfo=KST),
        indicators=IndicatorSnapshot(
            bb_upper=price * 1.05,
            bb_middle=price,
            bb_lower=price * 0.95,
            bb_width=0.1,
            bb_pct_b=0.5,
            cci=cci,
            volume_ratio=vr,
            bb_width_quantile=None,
        ),
    )
    text = format_message(sig)
    assert isinstance(text, str)
    assert len(text) > 0
    # 토큰 패턴 미포함
    assert not re.search(r"\d{5,}:[A-Za-z0-9_\-]{10,}", text)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2(M8) — sendPhoto 시나리오 4종
# ═══════════════════════════════════════════════════════════════════════════════

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # 최소 fake PNG


def _make_chart_file(tmp_path: Path, name: str = "chart.png") -> Path:
    f = tmp_path / name
    f.write_bytes(_PNG_BYTES)
    return f


# (M8-a) chart_path 정상 → sendPhoto multipart 호출
async def test_sendphoto_calls_sendphoto_endpoint(signal: Signal, tmp_path: Path) -> None:
    chart = _make_chart_file(tmp_path)
    tr = make_transport(200, _OK_BODY)
    notifier = make_notifier(tr)
    await notifier.send_signal(signal, chart_path=chart)

    assert len(tr.requests) == 1
    req = tr.requests[0]
    assert "/sendPhoto" in str(req.url)
    ct = req.headers.get("content-type", "")
    assert "multipart/form-data" in ct
    # caption 필드 이름이 바디에 존재
    assert b"caption" in req.content


# (M8-b) chart_path=None → M7 sendMessage 경로
async def test_no_chart_path_uses_sendmessage(signal: Signal) -> None:
    tr = make_transport(200, _OK_BODY)
    notifier = make_notifier(tr)
    await notifier.send_signal(signal, chart_path=None)

    assert len(tr.requests) == 1
    assert "/sendMessage" in str(tr.requests[0].url)


# (M8-c) sendPhoto 5xx → sendMessage fallback
async def test_sendphoto_5xx_falls_back_to_sendmessage(signal: Signal, tmp_path: Path) -> None:
    chart = _make_chart_file(tmp_path)

    def handler(req: httpx.Request) -> httpx.Response:
        if "/sendPhoto" in str(req.url):
            return httpx.Response(503, json={"ok": False})
        return httpx.Response(200, json=_OK_BODY)

    tr = _AsyncMockTransport(handler)
    notifier = make_notifier(tr, max_retries=3)
    with structlog.testing.capture_logs() as cap:
        await notifier.send_signal(signal, chart_path=chart)

    photo_reqs = [r for r in tr.requests if "/sendPhoto" in str(r.url)]
    msg_reqs = [r for r in tr.requests if "/sendMessage" in str(r.url)]
    assert len(photo_reqs) == 3   # sendPhoto 3회 재시도 후 소진
    assert len(msg_reqs) == 1     # sendMessage fallback 1회
    # fallback warning 로그 확인
    assert any("sendPhoto_failed_fallback" in str(e) for e in cap)


# (M8-d) caption 1024자 초과 → 잘림 + warning 로그
async def test_sendphoto_caption_truncated(signal: Signal, tmp_path: Path) -> None:
    from unittest.mock import patch

    chart = _make_chart_file(tmp_path)
    long_text = "가" * 600  # 6*(2) = probably > 1024 bytes but let's use pure ASCII
    long_text = "x" * 1100  # 1100 chars > 1024

    tr = make_transport(200, _OK_BODY)
    notifier = make_notifier(tr)

    with patch("signal_program.notifiers.telegram.format_message", return_value=long_text):
        with structlog.testing.capture_logs() as cap:
            await notifier.send_signal(signal, chart_path=chart)

    assert len(tr.requests) == 1
    body = tr.requests[0].content
    # caption 값이 잘렸는지 확인 — "x" * 1021 + "..." = 1024자
    assert body.count(b"x" * 10) > 0   # 잘린 caption 일부 포함
    assert b"x" * 1050 not in body      # 1050자 연속 없음 (잘림 확인)
    assert any("caption_truncated" in str(e) for e in cap)
