"""알림 송출 실패 이력 API (R-P1-8).

GET /api/notifications/failures  → list[FailureEntry]
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["notifications"])

_FAILURES_PATH = Path("state/notification_failures.jsonl")


class FailureEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    failed_at: datetime
    market: str
    error: str
    retries: int


@router.get("/api/notifications/failures", response_model=list[FailureEntry])
def list_failures(limit: int = 50) -> list[FailureEntry]:
    from signal_program.state.notification_log import NotificationFailureLog  # noqa: PLC0415

    log = NotificationFailureLog(_FAILURES_PATH)
    records = log.read_recent(limit=limit)
    entries: list[FailureEntry] = []
    for r in records:
        try:
            entries.append(FailureEntry.model_validate(r))
        except Exception:  # noqa: BLE001
            continue
    return entries
