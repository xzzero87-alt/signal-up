"""POST /api/feedback — 회고 라벨 기록 (ADR-0010 R_P1_10, G3 측정 인프라).

state/signal_feedback.jsonl 에 한 줄씩 append.
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

_KST = ZoneInfo("Asia/Seoul")
_FEEDBACK_FILE = Path(STATE_DIR) / "signal_feedback.jsonl"

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: str
    triggered_at: str          # ISO 8601 문자열 그대로 저장
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
