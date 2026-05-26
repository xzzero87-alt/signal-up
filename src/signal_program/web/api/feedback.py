"""회고 라벨 엔드포인트 (ADR-0010 R_P1_10, G3 측정 인프라).

POST /api/feedback          — 레거시 👍/👎 라벨 (기존 테스트 유지)
POST /api/signals/{id}/feedback — 신규 카드 뷰 회고 (R_P1_10)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from signal_program.constants import STATE_DIR
from signal_program.state.signal_feedback import save_feedback

_KST = ZoneInfo("Asia/Seoul")
_FEEDBACK_FILE = Path(STATE_DIR) / "signal_feedback.jsonl"

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: str
    triggered_at: str  # ISO 8601 문자열 그대로 저장
    label: Literal["👍", "👎"]


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


@router.post("/feedback", response_model=FeedbackResponse)
async def post_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """시그널 회고 라벨을 JSONL에 기록한다.

    G3 측정 (D+14): label=👍 비율 / V2 발사 비율 교차 분석.
    """
    record = {
        "recorded_at": datetime.now(_KST).isoformat(),
        "market": body.market,
        "triggered_at": body.triggered_at,
        "label": body.label,
    }
    _FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return FeedbackResponse(ok=True)


# ── 신규: 카드 뷰 회고 (R_P1_10) ─────────────────────────────────────────────


class _SignalFeedbackBody(BaseModel):
    """POST /api/signals/{signal_id}/feedback 요청 바디."""

    model_config = ConfigDict(extra="forbid")
    feedback: Literal["helpful", "confusing", "bad"]


class _SignalFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal_id: str
    feedback: str
    ok: bool


@router.post("/signals/{signal_id}/feedback", response_model=_SignalFeedbackResponse)
async def submit_signal_feedback(
    signal_id: str,
    body: _SignalFeedbackBody,
) -> _SignalFeedbackResponse:
    """카드 뷰 회고 라벨을 저장한다 (R_P1_10).

    signal_id = "{triggered_at_iso}_{market}" 포맷.
    market 은 signal_id 끝 underscore 이후 부분에서 추출.
    """
    parts = signal_id.rsplit("_", 1)
    market = parts[1] if len(parts) == 2 else "UNKNOWN"  # noqa: PLR2004
    save_feedback(signal_id=signal_id, market=market, feedback=body.feedback)
    return _SignalFeedbackResponse(signal_id=signal_id, feedback=body.feedback, ok=True)
