"""GET /api/health — 서비스 헬스체크."""

from __future__ import annotations

import importlib.metadata

from fastapi import APIRouter

from signal_program.web.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        version = importlib.metadata.version("signal-program")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    return HealthResponse(status="ok", version=version)
