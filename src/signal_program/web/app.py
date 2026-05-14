"""FastAPI 앱 팩토리 — M14 (Jinja2 + StaticFiles 추가).

create_app(settings_path): 테스트·서빙 양방향 사용.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from signal_program.config import Settings
from signal_program.web.api import backtest, daemon, dashboard, health, pages, settings, signals
from signal_program.web.deps import init_settings_store
from signal_program.web.security import friendly_validation_errors

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    settings_path: Path | None = None,
    env_settings: Settings | None = None,
) -> FastAPI:
    """FastAPI 앱 생성. settings_path 미지정 시 state/settings.json 기본."""
    app = FastAPI(title="업비트 시그널 프로그램", version="v2.0", docs_url="/api/docs")

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            status_code=422,
            content={"detail": friendly_validation_errors(exc)},
        )

    _settings_path = settings_path or Path("state/settings.json")
    _env = env_settings or Settings()
    init_settings_store(_settings_path, _env)

    # API 라우터 먼저 등록 (/api/* 가 HTML 페이지보다 우선)
    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(signals.router)
    app.include_router(backtest.router)
    app.include_router(daemon.router)
    app.include_router(dashboard.router)

    # 정적 파일
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # HTML 페이지 라우터 (나중 등록)
    app.include_router(pages.router)

    return app
