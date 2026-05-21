"""SignalHistory — 시그널 이력 JSONL 영속화 (state/signals.jsonl, ADR-0012).

각 줄: {"signal": {...}, "sent_at": "<iso8601_kst>"}
1MB 초과 시 signals.1.jsonl 로 rotate.

import 사용처:
  - web/api/signals.py (set_signal_history → read_recent)
  - runner.py 콜백 (append)
"""

from __future__ import annotations

import json
import os
import platform
import threading
from pathlib import Path  # noqa: TC003
from typing import Any

_MAX_BYTES = 1024 * 1024  # 1 MB


class SignalHistory:
    """JSON Lines 파일에 시그널 기록. threading.Lock으로 동시 append 안전."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, signal_dict: dict[str, Any]) -> None:
        """시그널 1건 기록. 1MB 초과 시 rotate 후 append."""
        with self._lock:
            self._rotate_if_needed()
            record = {"signal": signal_dict}
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
            if platform.system() != "Windows":
                os.chmod(self._path, 0o600)

    def read_recent(
        self,
        limit: int = 50,
        market: str | None = None,
        direction: str | None = None,
        mode: str | None = None,
        strength: str | None = None,
    ) -> list[dict[str, Any]]:
        """최근 N건 반환. 필터 지정 시 일치 항목만."""
        if not self._path.exists():
            return []

        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        records: list[dict[str, Any]] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue

            sig = record.get("signal", {})
            if market and sig.get("market") != market:
                continue
            if direction and sig.get("direction") != direction:
                continue
            if mode and sig.get("mode") != mode:
                continue
            if strength and sig.get("strength") != strength:
                continue

            records.append(record)
            if len(records) >= limit:
                break

        return list(reversed(records))

    def _rotate_if_needed(self) -> None:
        """1MB 초과 시 현재 파일을 .1.jsonl 로 이동."""
        if not self._path.exists():
            return
        if self._path.stat().st_size < _MAX_BYTES:
            return

        rotated = self._path.parent / (self._path.stem + ".1.jsonl")
        if rotated.exists():
            rotated.unlink()
        self._path.rename(rotated)
