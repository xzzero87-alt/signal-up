"""Notifier Protocol — DESIGN.md §8.4."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from signal_program.models import Signal


class Notifier(Protocol):
    """텔레그램 등 알림 채널 추상화. 시그니처 변경 금지(DESIGN.md §8.4)."""

    async def send_signal(self, signal: "Signal", chart_path: Path | None) -> None: ...
