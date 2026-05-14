"""FastAPI 앱 팩토리 — M13 골격.

create_app(settings_path): 테스트·서빙 양방향 사용.
M14에서 Jinja2Templates + StaticFiles 마운트 추가.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from signal_program.config import Settings
from signal_program.web.api import backtest, daemon, dashboard, health, settings, signals
from signal_program.web.deps import init_settings_store


def create_app(
    settings_path: Path | None = None,
    env_settings: Settings | None = None,
) -> FastAPI:
    """FastAPI 앱 생성. settings_path 미지정 시 state/settings.json 기본."""
    app = FastAPI(
        title="업비트 시그널 프로그램",
        version="v2.0",
        docs_url="/api/docs",
    )

    _settings_path = settings_path or Path("state/settings.json")
    _env = env_settings or Settings()
    init_settings_store(_settings_path, _env)

    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(signals.router)
    app.include_router(backtest.router)
    app.include_router(daemon.router)
    app.include_router(dashboard.router)

    return app
