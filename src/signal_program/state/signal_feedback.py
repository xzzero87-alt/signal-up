"""회고 라벨 저장소 (ADR-0010 R_P1_10).

state/signal_feedback.jsonl 에 추가 쓰기.
레코드 형식: {"signal_id": ..., "market": ..., "feedback": ..., "labeled_at": ...}

기존 POST /api/feedback 가 같은 파일에 쓰는 레코드와 공존함.
(기존 레코드는 signal_id 키가 없으므로 load_feedback_map 에서 자동 skip.)

import 사용처:
  - web/api/feedback.py (save_feedback)
  - web/api/signals.py  (load_feedback_map)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from signal_program.constants import STATE_DIR

_FEEDBACK_FILE = Path(STATE_DIR) / "signal_feedback.jsonl"


def build_signal_id(triggered_at_iso: str, market: str) -> str:
    """signal_id 조립 헬퍼. 세 곳(저장·조회·프론트)에서 동일 포맷 보장.

    형식: ``{triggered_at_iso}_{market}``
    예시: ``2026-01-01T09:00:00+09:00_KRW-BTC``
    """
    return f"{triggered_at_iso}_{market}"


def save_feedback(signal_id: str, market: str, feedback: str) -> None:
    """feedback을 signal_feedback.jsonl 에 추가 기록한다."""
    _FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "signal_id": signal_id,
        "market": market,
        "feedback": feedback,
        "labeled_at": datetime.now(tz=UTC).isoformat(),
    }
    with _FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_feedback_map() -> dict[str, str]:
    """signal_id → 최신 feedback 매핑을 반환한다.

    파일이 없거나 비어있으면 빈 dict 반환.
    같은 signal_id 에 여러 항목이 있으면 마지막(최신) 값이 우선.
    """
    if not _FEEDBACK_FILE.exists():
        return {}
    result: dict[str, str] = {}
    with _FEEDBACK_FILE.open(encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
                sid = entry.get("signal_id")
                fb = entry.get("feedback")
                if sid and fb:
                    result[sid] = fb
            except (json.JSONDecodeError, AttributeError):
                continue
    return result
