"""알림 송출 실패 이력 저장소 (R-P1-8).

NotificationFailureLog: JSONL 파일 기반 실패 기록 + 최근 조회.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class NotificationFailureLog:
    """텔레그램 알림 실패 이력을 JSONL 파일에 기록한다."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, *, market: str, error: str, retries: int) -> None:
        record = {
            "failed_at": datetime.now(UTC).isoformat(),
            "market": market,
            "error": error,
            "retries": retries,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_recent(self, limit: int = 50) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, object]] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= limit:
                break
        return records
