"""차트 이미지 제공 엔드포인트 (R-P1-7).

GET /api/charts/{filename}  → PNG FileResponse | 404
파일명은 {MARKET}_{YYYYMMDDTHHMM}.png 패턴만 허용.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

if TYPE_CHECKING:
    from pathlib import Path
from fastapi.responses import FileResponse

router = APIRouter(tags=["charts"])

_SAFE_PATTERN = re.compile(r"^[A-Z0-9_]+_\d{8}T\d{4}\.png$")


def _get_charts_dir(request: Request) -> Path:
    return request.app.state.charts_dir  # type: ignore[no-any-return]


@router.get("/api/charts/{filename}", response_class=FileResponse)
def get_chart(filename: str, request: Request) -> FileResponse:
    if not _SAFE_PATTERN.match(filename):
        raise HTTPException(status_code=404, detail="Not found")
    charts_dir = _get_charts_dir(request)
    path = (charts_dir / filename).resolve()
    if not path.exists() or path.parent.resolve() != charts_dir.resolve():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path=str(path), media_type="image/png")
