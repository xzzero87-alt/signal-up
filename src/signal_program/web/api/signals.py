"""시그널 조회 엔드포인트.

GET /api/signals/recent — 원본 JSONL 레코드 반환 (기존, 변경 금지)
GET /api/signals/cards  — 카드 뷰용 SignalCardEntry 반환 (R_P1_9 신규)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from signal_program.state.signal_feedback import (
    build_signal_id,
    compute_feedback_stats,
    load_feedback_map,
)
from signal_program.web.schemas import FeedbackStats, SignalCardEntry

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


@router.get("/api/signals/cards", response_model=list[SignalCardEntry])
def signal_cards(
    market: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    strength: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[SignalCardEntry]:
    """카드 뷰용 시그널 목록. feedback 상태 포함 (R_P1_9)."""
    if _signal_history is None:
        return []
    records = _signal_history.read_recent(  # type: ignore[attr-defined]
        limit=limit, market=market, direction=direction, mode=mode, strength=strength
    )
    feedback_map = load_feedback_map()
    entries: list[SignalCardEntry] = []
    for record in records:
        sig: dict[str, Any] = record.get("signal", {})
        market_val: str = str(sig.get("market", ""))
        triggered_at_iso: str = str(sig.get("triggered_at", ""))
        mode_code: str = str(sig.get("mode", "A"))
        indicators: dict[str, Any] = sig.get("indicators", {})

        signal_id = build_signal_id(triggered_at_iso, market_val)
        mode_label = "V2" if mode_code == "C" else "V1"

        try:
            triggered_at_dt = datetime.fromisoformat(triggered_at_iso)
        except (ValueError, TypeError):
            continue

        entries.append(
            SignalCardEntry(
                signal_id=signal_id,
                market=market_val,
                triggered_at=triggered_at_dt,
                mode=mode_label,
                direction=str(sig.get("direction", "buy")),
                strength=str(sig.get("strength", "normal")),
                price=float(sig.get("price", 0.0)),
                bb_pct_b=float(indicators.get("bb_pct_b", 0.0)),
                cci=float(indicators.get("cci", 0.0)),
                volume_ratio=float(indicators.get("volume_ratio", 0.0)),
                sparkline_prices=None,
                feedback=feedback_map.get(signal_id),
            )
        )
    return entries


@router.get("/api/signals/stats", response_model=FeedbackStats)
async def get_signal_stats(
    window: int = Query(default=30, ge=1, le=200),
) -> FeedbackStats:
    """피드백 누적 통계를 반환한다. sticky 패널 거짓신호율 배지에 사용된다 (R_P1_14)."""
    raw: dict[str, Any] = compute_feedback_stats(window=window)
    return FeedbackStats(
        bad_count=int(raw["bad_count"]),
        total_count=int(raw["total_count"]),
        bad_rate=float(raw["bad_rate"]),
        window=int(raw["window"]),
        has_data=bool(raw["has_data"]),
    )
