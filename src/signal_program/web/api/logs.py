"""GET /api/logs — 데몬 로그 파일 tail 조회 (read-only).

system.html 의 로그 뷰어가 호출한다. 응답은 줄 문자열의 배열.
시크릿 마스킹은 기록 시점(logging_config)에 이미 적용되므로 그대로 반환한다.
파일이 없으면 빈 목록을 반환해 페이지가 "(로그 없음)"으로 표시한다.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path  # noqa: TC003

from fastapi import APIRouter, Query, Request

router = APIRouter(tags=["logs"])


@router.get("/api/logs", response_model=list[str])
def get_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[str]:
    """로그 파일의 마지막 limit 줄을 반환."""
    log_path: Path = request.app.state.logs_path
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        tail = deque(f, maxlen=limit)
    return [line.rstrip("\n") for line in tail]
