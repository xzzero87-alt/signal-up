"""AI 시그널 컨텍스트 보강 서비스 — ADR-0020.

시그널 발송 성공 후 asyncio.create_task로 비차단 실행.
실패·타임아웃은 삼키고 로그만 남긴다 — enrichment가 시그널을 지연·차단하는 일 없음.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import httpx
import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from signal_program.config import Settings
    from signal_program.models import Signal

log = structlog.get_logger()

_KST = ZoneInfo("Asia/Seoul")
_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"

# 변경 금지 (ADR-0020 §Decision 3)
_SYSTEM_PROMPT = (
    "당신은 암호화폐 시장 뉴스 요약가입니다. "
    "최근 24시간 해당 자산 관련 핵심 뉴스나 이벤트를 한국어로 2~3문장으로 요약하세요. "
    "각 사실 끝에 (출처도메인) 형식으로 출처를 표기하세요. "
    "매수·매도 권유, 확률, 목표가는 절대 언급하지 마세요. "
    "관련 뉴스가 없으면 '특이 뉴스 없음'이라고만 답하세요."
)


class AiEnrichmentService:
    """Claude API(web_search)로 시그널 컨텍스트를 보강하고 텔레그램 후속 메시지를 발송."""

    def __init__(
        self,
        settings: Settings,
        notify_text: Callable[[str], Awaitable[None]],
        *,
        _client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._notify_text = notify_text
        self._client = _client
        self._daily_count: int = 0
        self._count_date: date | None = None

    def _reset_if_new_day(self) -> None:
        today = datetime.now(_KST).date()
        if self._count_date != today:
            self._count_date = today
            self._daily_count = 0

    def _mask_key(self) -> str:
        key = self._settings.anthropic_api_key
        return "••••" + key[-4:] if len(key) >= 4 else "••••"

    async def enrich(self, signal: Signal) -> None:
        self._reset_if_new_day()

        if self._daily_count >= self._settings.ai_enrichment_daily_cap:
            log.info("enrichment_cap_reached", market=signal.market, date=str(self._count_date))
            return

        try:
            await self._call_and_notify(signal)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "enrichment_failed",
                market=signal.market,
                exc_type=type(exc).__name__,
                api_key_hint=self._mask_key(),
            )

    async def _call_and_notify(self, signal: Signal) -> None:
        payload = {
            "model": self._settings.ai_enrichment_model,
            "max_tokens": 500,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"시장: {signal.market}, "
                        f"방향: {signal.direction.value}, "
                        f"모드: {signal.mode.value}, "
                        f"강도: {signal.strength.value}, "
                        f"가격: {signal.price:,.0f}원"
                    ),
                }
            ],
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 2,
                }
            ],
        }
        headers = {
            "x-api-key": self._settings.anthropic_api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        if self._client is not None:
            resp = await self._client.post(_API_URL, json=payload, headers=headers)
        else:
            timeout = float(self._settings.ai_enrichment_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(_API_URL, json=payload, headers=headers)

        resp.raise_for_status()
        data = resp.json()

        text = "\n".join(
            block["text"] for block in data.get("content", []) if block.get("type") == "text"
        )

        usage = data.get("usage", {})
        self._daily_count += 1
        log.info(
            "enrichment_ok",
            market=signal.market,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

        message = f"🤖 AI 컨텍스트 — {signal.market}\n{text}\n— 정보 제공 목적, 투자 판단 아님"
        await self._notify_text(message)
