"""GET /api/signals/recent — 최근 시그널 조회.

M13: 빈 배열 stub
M14: state/signals.jsonl에서 실 데이터 제공
"""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(tags=["signals"])

_signal_history: object | None = None


def set_signal_history(history: object) -> None:
    """M14에서 app 기동 시 SignalHistory 인스턴스 주입."""
    global _signal_history  # noqa: PLW0603
    _signal_history = history


@router.get("/api/signals/recent")
def recent_signals(
    market: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    strength: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[object]:
    if _signal_history is None:
        return []
    records = _signal_history.read_recent(  # type: ignore[attr-defined]
        limit=limit, market=market, direction=direction, mode=mode, strength=strength
    )
    return list(records)
