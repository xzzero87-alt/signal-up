"""모멘텀(M2) 대시보드 API — ADR-0031.

GET /api/momentum/dashboard → 최근 저장된 유니버스·포트폴리오 상태(state/momentum_*.json)를
그대로 반환한다. 잡이 아직 한 번도 안 돌았으면 빈 값.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/momentum", tags=["momentum"])

_UNIVERSE_PATH = Path("state/momentum_universe.json")
_PORTFOLIO_PATH = Path("state/momentum_portfolio.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return None
    return data


@router.get("/dashboard")
def momentum_dashboard() -> dict[str, Any]:
    """현재 포트폴리오·유니버스 요약."""
    universe = _read_json(_UNIVERSE_PATH)
    portfolio = _read_json(_PORTFOLIO_PATH)
    return {
        "universe": universe or {"year": None, "codes": [], "computed_at": None},
        "portfolio": portfolio
        or {"codes": [], "asof": None, "updated_at": None, "added": [], "removed": []},
    }
