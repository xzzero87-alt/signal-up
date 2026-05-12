"""TelegramNotifier — DESIGN.md §5.3(메시지 포맷) §5.5(통신 정책).

M7 범위: sendMessage(텍스트)만. sendPhoto(차트) 및 fallback은 M8에서 추가.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx
    from pydantic import SecretStr
    from signal_program.models import Signal


class TelegramNotifier:
    """텔레그램 봇을 통한 시그널 알림 전송.

    DESIGN.md §5.3 메시지 포맷 / §5.5 통신 정책(httpx, 재시도, 마스킹) 준수.
    chart_path 파라미터는 수신만 하고 무시 — TODO(M8): sendPhoto 분기 추가.
    """

    def __init__(
        self,
        bot_token: "SecretStr",
        chat_id: str,
        *,
        dry_run: bool = False,
        timeout: float = 10.0,
        max_retries: int = 3,
        http_client: "httpx.AsyncClient | None" = None,
        _retry_wait_multiplier: float = 1.0,
    ) -> None:
        raise NotImplementedError

    async def send_signal(self, signal: "Signal", chart_path: Path | None = None) -> None:
        """시그널 텔레그램 전송. 실패 시 예외 없이 로깅(§5.5)."""
        raise NotImplementedError
