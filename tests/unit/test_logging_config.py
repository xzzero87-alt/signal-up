"""logging_config 유닛 테스트 (마일스톤 1-b)."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import MutableMapping

import structlog

from signal_program.config import Settings
from signal_program.logging_config import (
    bind_contextvars,
    clear_contextvars,
    configure_logging,
    mask_secrets,
)


def _make_settings(**kwargs: Any) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def test_configure_logging_runs_without_error() -> None:
    settings = _make_settings()
    configure_logging(settings)
    logger = structlog.get_logger("test")
    logger.info("probe")  # 예외 없이 실행되어야 한다


def test_mask_secrets_redacts_telegram_token() -> None:
    token = "1234567890:AAFabcdefghijklmnopqrstuvwxyz5678"
    event: MutableMapping[str, Any] = {"event": f"토큰={token}"}
    result = mask_secrets(None, "info", event)
    assert "1234567890" not in str(result["event"])
    assert "••••••••" in str(result["event"])
    assert str(result["event"]).endswith("5678")


def test_mask_secrets_leaves_non_token_strings_intact() -> None:
    event: MutableMapping[str, Any] = {"event": "일반 로그 메시지"}
    result = mask_secrets(None, "info", event)
    assert result["event"] == "일반 로그 메시지"


def test_contextvars_roundtrip() -> None:
    clear_contextvars()
    bind_contextvars(cycle_id="abc-123", market="KRW-BTC")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx.get("cycle_id") == "abc-123"
    assert ctx.get("market") == "KRW-BTC"
    clear_contextvars()
    ctx_after = structlog.contextvars.get_contextvars()
    assert "cycle_id" not in ctx_after
    assert "market" not in ctx_after


def test_attach_file_handler_creates_rotating_handler(tmp_path: Path) -> None:
    """attach_file_handler가 RotatingFileHandler를 루트 로거에 부착한다 (ADR-0013)."""
    from signal_program.logging_config import attach_file_handler

    log_file = tmp_path / "logs" / "daemon.log"
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    try:
        attach_file_handler(log_file)

        assert log_file.parent.exists()
        rotating = [
            h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(rotating) >= 1
        rh = rotating[-1]
        assert rh.maxBytes == 5 * 1024 * 1024
        assert rh.backupCount == 7
    finally:
        # 핸들러 원상 복구 (다른 테스트 격리)
        for h in root.handlers:
            if h not in handlers_before:
                h.close()
        root.handlers = handlers_before
        # structlog PrintLoggerFactory 원상 복구
        structlog.configure(
            logger_factory=structlog.PrintLoggerFactory(sys.stdout),
            cache_logger_on_first_use=True,
        )
