"""HTML 페이지 라우터 — M14."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from signal_program.state.settings_store import SettingsStore  # noqa: TC001
from signal_program.web.api.settings import _to_view
from signal_program.web.deps import get_settings_store
from signal_program.web.help_text import SETTING_HELP

_TEMPLATE_DIR = Path(__file__).parents[1] / "templates"

router = APIRouter(include_in_schema=False)

_jinja_env: Environment | None = None


def _env() -> Environment:
    global _jinja_env  # noqa: PLW0603
    if _jinja_env is None:
        _jinja_env = Environment(
            autoescape=True,
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        )
    return _jinja_env


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,  # noqa: ARG001
    market: str = "",
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    html = _env().get_template("index.html").render(active="dashboard", market=market or "crypto")
    return HTMLResponse(content=html)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,  # noqa: ARG001
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    view = _to_view(store.load())
    html = (
        _env()
        .get_template("settings.html")
        .render(
            active="settings",
            settings=view.model_dump(),
            help=SETTING_HELP,
        )
    )
    return HTMLResponse(content=html)


@router.get("/failures", response_class=HTMLResponse)
def failures_page(
    request: Request,  # noqa: ARG001
) -> HTMLResponse:
    html = _env().get_template("failures.html").render(active="failures")
    return HTMLResponse(content=html)


@router.get("/backtest", response_class=HTMLResponse)
def backtest_page(
    request: Request,  # noqa: ARG001
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    settings_data = store.load()
    html = (
        _env()
        .get_template("backtest.html")
        .render(
            active="backtest",
            whitelist_markets=list(settings_data.whitelist_markets),
            kr_whitelist_symbols=list(settings_data.kr_whitelist_symbols),
        )
    )
    return HTMLResponse(content=html)


@router.get("/system", response_class=HTMLResponse)
def system_page(
    request: Request,  # noqa: ARG001
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    view = _to_view(store.load())
    html = (
        _env()
        .get_template("system.html")
        .render(
            active="system",
            settings=view.model_dump(),
            help=SETTING_HELP,
        )
    )
    return HTMLResponse(content=html)


@router.get("/_styleguide", response_class=HTMLResponse)
def styleguide_page(
    request: Request,  # noqa: ARG001
) -> HTMLResponse:
    # 개발 전용 (collaboration-prd.md R3 / §7-Q2). 기본 노출, 운영에서 끄려면
    # 환경변수 SIGNAL_STYLEGUIDE=0 설정.
    if os.environ.get("SIGNAL_STYLEGUIDE", "1") == "0":
        raise HTTPException(status_code=404)
    html = _env().get_template("styleguide.html").render(active="styleguide")
    return HTMLResponse(content=html)
