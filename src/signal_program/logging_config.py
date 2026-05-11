"""structlog 설정 - KST 타임스탬프, JSON/콘솔 출력, 시크릿 마스킹.

configure_logging(settings)을 CLI 진입 시점에 한 번 호출한다.
"""

from __future__ import annotations

import logging
import re
import sys
import zoneinfo
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from signal_program.config import Settings

_KST = zoneinfo.ZoneInfo("Asia/Seoul")

# 텔레그램 봇 토큰 패턴: {bot_id}:{key}
_TOKEN_RE = re.compile(r"\d{5,15}:[A-Za-z0-9_\-]{20,50}")

# 상관 키 컨텍스트변수 헬퍼 (cycle_id, market, mode, direction, request_id)
bind_contextvars = structlog.contextvars.bind_contextvars
unbind_contextvars = structlog.contextvars.unbind_contextvars
clear_contextvars = structlog.contextvars.clear_contextvars


def _add_kst_timestamp(
    _logger: Any,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """이벤트 딕셔너리에 KST ISO 8601 타임스탬프를 추가한다."""
    event_dict["timestamp"] = datetime.now(_KST).isoformat(timespec="milliseconds")
    return event_dict


def mask_secrets(
    _logger: Any,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """텔레그램 봇 토큰 패턴을 ••••••••XXXX 형식으로 마스킹한다."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = _TOKEN_RE.sub(
                lambda m: "••••••••" + m.group(0)[-4:],
                value,
            )
    return event_dict


def configure_logging(settings: Settings) -> None:
    """structlog을 초기화한다.

    LOG_LEVEL=DEBUG -> 콘솔 친화 출력 (colors=True)
    그 외 -> JSON 줄 출력
    """
    log_level: int = getattr(logging, settings.log_level.upper(), logging.INFO)
    is_debug = settings.log_level.upper() == "DEBUG"

    renderer: Any = (
        structlog.dev.ConsoleRenderer(colors=True)
        if is_debug
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            _add_kst_timestamp,
            mask_secrets,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", level=log_level, force=True)
