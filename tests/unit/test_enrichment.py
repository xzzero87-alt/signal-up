"""AiEnrichmentService 단위 테스트 (ADR-0020)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import structlog.testing

from signal_program.config import Settings
from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import IndicatorSnapshot, Signal

pytestmark = pytest.mark.anyio


def _make_signal() -> Signal:
    return Signal(
        market="KRW-BTC",
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.STRONG,
        price=50_000_000.0,
        triggered_at=datetime.now(UTC),
        indicators=IndicatorSnapshot(
            bb_upper=52_000_000.0,
            bb_middle=50_000_000.0,
            bb_lower=48_000_000.0,
            bb_width=0.04,
            bb_pct_b=0.5,
            cci=100.0,
            volume_ratio=1.5,
        ),
    )


def _make_settings(**kwargs: object) -> Settings:
    defaults: dict[str, object] = {
        "anthropic_api_key": "sk-ant-test1234",
        "ai_enrichment_enabled": True,
    }
    defaults.update(kwargs)
    return Settings(_env_file=None, **defaults)  # type: ignore[call-arg]


def _ok_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "BTC 호재 뉴스 (example.com)."}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        )

    return httpx.MockTransport(handler)


def _error_transport(status: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    return httpx.MockTransport(handler)


# ── 정상 응답 ─────────────────────────────────────────────────────────────────


async def test_enrich_ok_calls_notify() -> None:
    from signal_program.enrichment import AiEnrichmentService

    calls: list[str] = []

    async def notify(text: str) -> None:
        calls.append(text)

    client = httpx.AsyncClient(transport=_ok_transport())
    svc = AiEnrichmentService(_make_settings(), notify, _client=client)
    await svc.enrich(_make_signal())

    assert len(calls) == 1
    assert calls[0].startswith("🤖 AI 컨텍스트 — KRW-BTC")
    assert "정보 제공 목적, 투자 판단 아님" in calls[0]
    assert "BTC 호재 뉴스 (example.com)." in calls[0]


# ── API 오류 격리 ──────────────────────────────────────────────────────────────


async def test_enrich_api_500_no_raise() -> None:
    from signal_program.enrichment import AiEnrichmentService

    calls: list[str] = []

    async def notify(text: str) -> None:
        calls.append(text)

    client = httpx.AsyncClient(transport=_error_transport(500))
    svc = AiEnrichmentService(_make_settings(), notify, _client=client)
    await svc.enrich(_make_signal())  # 예외 전파 없어야 함

    assert calls == []


# ── 타임아웃 격리 ──────────────────────────────────────────────────────────────


async def test_enrich_timeout_no_raise() -> None:
    from signal_program.enrichment import AiEnrichmentService

    calls: list[str] = []

    async def notify(text: str) -> None:
        calls.append(text)

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))
    svc = AiEnrichmentService(_make_settings(), notify, _client=client)
    await svc.enrich(_make_signal())  # 예외 전파 없어야 함

    assert calls == []


# ── 일일 cap ──────────────────────────────────────────────────────────────────


async def test_enrich_cap_no_http_call() -> None:
    from datetime import date

    from signal_program.enrichment import AiEnrichmentService

    request_count = 0

    def counting_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"content": [], "usage": {}})

    async def notify(text: str) -> None:
        pass

    settings = _make_settings(ai_enrichment_daily_cap=2)
    client = httpx.AsyncClient(transport=httpx.MockTransport(counting_handler))
    svc = AiEnrichmentService(settings, notify, _client=client)

    svc._daily_count = 2
    svc._count_date = date.today()

    await svc.enrich(_make_signal())

    assert request_count == 0


async def test_enrich_cap_resets_after_midnight() -> None:
    """KST 자정 경과 후 카운터가 리셋되어 정상 발송된다."""
    from datetime import date

    from freezegun import freeze_time

    from signal_program.enrichment import AiEnrichmentService

    calls: list[str] = []

    async def notify(text: str) -> None:
        calls.append(text)

    client = httpx.AsyncClient(transport=_ok_transport())
    settings = _make_settings(ai_enrichment_daily_cap=1)
    svc = AiEnrichmentService(settings, notify, _client=client)

    svc._daily_count = 1
    svc._count_date = date(2026, 6, 10)

    with freeze_time("2026-06-11 00:00:01+09:00"):
        await svc.enrich(_make_signal())

    assert len(calls) == 1


# ── 보안: API 키 로그 미노출 ──────────────────────────────────────────────────


async def test_api_key_not_in_log() -> None:
    from signal_program.enrichment import AiEnrichmentService

    async def notify(text: str) -> None:
        pass

    api_key = "sk-ant-secret-key-12345"
    settings = _make_settings(anthropic_api_key=api_key)
    client = httpx.AsyncClient(transport=_error_transport(500))
    svc = AiEnrichmentService(settings, notify, _client=client)

    with structlog.testing.capture_logs() as captured:
        await svc.enrich(_make_signal())

    for entry in captured:
        for v in entry.values():
            assert api_key not in str(v), f"API key leaked in log: {entry}"
