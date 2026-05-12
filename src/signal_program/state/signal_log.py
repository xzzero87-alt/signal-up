"""SignalLog — 시그널 송출 이력 JSON Lines 기록 (state/signals.jsonl).

각 줄: {"signal": {...}, "sent_status": "ok|dry_run|cooled_down", "sent_at": "<iso8601_kst>"}
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from datetime import datetime

    from signal_program.models import Signal

log = structlog.get_logger()


class SignalLog:
    """JSON Lines 파일에 시그널 기록 — asyncio.Lock으로 동시 append 안전."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def append(self, signal: Signal, sent_status: str, sent_at: datetime) -> None:
        """시그널 1건 기록. 실패해도 예외 없이 structlog error만."""
        record = {
            "signal": signal.model_dump(mode="json"),
            "sent_status": sent_status,
            "sent_at": sent_at.isoformat(),
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        async with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line)
                if platform.system() != "Windows":
                    os.chmod(self._path, 0o600)
            except OSError as exc:
                log.error("signal_log_write_failed", path=str(self._path), error=str(exc))
