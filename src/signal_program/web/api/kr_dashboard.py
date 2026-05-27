"""국장 대시보드 API — M20.

GET /api/kr/dashboard  → KrDashboardView
GET /api/kr/signals    → list[dict] (timeframe 필터 지원)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from signal_program.web.api.signals import recent_signals
from signal_program.web.schemas import KrDashboardView

router = APIRouter(prefix="/api/kr", tags=["kr-dashboard"])


def _is_kr_signal(record: Any) -> bool:
    """국장 시그널 여부 — market이 'KRW-'로 시작하지 않으면 국장."""
    if not isinstance(record, dict):
        return False
    sig = record.get("signal", {})
    if not isinstance(sig, dict):
        return False
    market: str = str(sig.get("market", ""))
    return bool(market) and not market.startswith("KRW-")


@router.get("/dashboard", response_model=KrDashboardView)
def kr_dashboard() -> KrDashboardView:
    """국장 대시보드 요약.

    stock_states: KrStockRunnerService에 실시간 캐시가 없으므로 빈 튜플.
    recent_signals: signal_history에서 국장 시그널만 필터링.
    """
    all_records = recent_signals(limit=50)
    kr_records = [r for r in all_records if _is_kr_signal(r)]

    return KrDashboardView(
        next_scan_at=None,
        last_scan_at=None,
        stock_states=(),
        recent_signals=tuple(kr_records),  # type: ignore[arg-type]
    )


@router.get("/signals")
def kr_signals(
    timeframe: str | None = Query(default=None, description="'60' 또는 '120'"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[Any]:
    """국장 시그널 목록. timeframe 필터 지원."""
    all_records = recent_signals(limit=limit)
    result: list[Any] = []
    for record in all_records:
        if not _is_kr_signal(record):
            continue
        if timeframe is not None:
            sig: dict[str, Any] = record.get("signal", {})  # type: ignore[union-attr]
            if str(sig.get("timeframe", "")) != timeframe:
                continue
        result.append(record)
    return result
