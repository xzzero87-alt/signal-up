"""HTML 페이지 라우터 — M14."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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


def _nav_flags(store: SettingsStore) -> dict[str, bool]:
    """사이드바·랜딩 표면 게이트 플래그 — base.html을 렌더하는 모든 페이지 공유 컨텍스트.

    미주입 시 Jinja에서 undefined(=falsy)로 취급돼 링크가 사라지므로 전 라우트에 주입한다.
    bar_enabled = 코인/국장 봉단위 라이브 표면(대시보드) 노출 여부.
    """
    s = store.load()
    return {
        "coin_enabled": s.coin_enabled,
        "kr_enabled": s.kr_enabled,
        "momentum_enabled": s.momentum_enabled,
        "bar_enabled": s.coin_enabled or s.kr_enabled,
    }


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,  # noqa: ARG001
    market: str = "",
    store: SettingsStore = Depends(get_settings_store),
) -> Response:
    flags = _nav_flags(store)
    # 봉단위 라이브가 꺼져 있고 모멘텀만 활성이면 봉단위 대시보드 대신 모멘텀으로.
    if not flags["bar_enabled"] and flags["momentum_enabled"]:
        return RedirectResponse(url="/momentum", status_code=307)
    html = (
        _env()
        .get_template("index.html")
        .render(active="dashboard", market=market or "crypto", **flags)
    )
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
            **_nav_flags(store),
        )
    )
    return HTMLResponse(content=html)


@router.get("/failures", response_class=HTMLResponse)
def failures_page(
    request: Request,  # noqa: ARG001
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    html = _env().get_template("failures.html").render(active="failures", **_nav_flags(store))
    return HTMLResponse(content=html)


@router.get("/momentum", response_class=HTMLResponse)
def momentum_page(
    request: Request,  # noqa: ARG001
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    html = _env().get_template("momentum.html").render(active="momentum", **_nav_flags(store))
    return HTMLResponse(content=html)


@router.get("/backtest", response_class=HTMLResponse)
def backtest_page(
    request: Request,  # noqa: ARG001
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    from signal_program.data.kr_universe import KR_UNIVERSE

    settings_data = store.load()
    _kr_name = {s.code: s.name for s in KR_UNIVERSE}
    kr_options = [
        {"code": c, "name": _kr_name.get(c, "")} for c in settings_data.kr_whitelist_symbols
    ]
    html = (
        _env()
        .get_template("backtest.html")
        .render(
            active="backtest",
            whitelist_markets=list(settings_data.whitelist_markets),
            kr_options=kr_options,
            **_nav_flags(store),
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
            **_nav_flags(store),
        )
    )
    return HTMLResponse(content=html)


@router.get("/_styleguide", response_class=HTMLResponse)
def styleguide_page(
    request: Request,  # noqa: ARG001
    store: SettingsStore = Depends(get_settings_store),
) -> HTMLResponse:
    # 개발 전용 (collaboration-prd.md R3 / §7-Q2). 기본 노출, 운영에서 끄려면
    # 환경변수 SIGNAL_STYLEGUIDE=0 설정.
    if os.environ.get("SIGNAL_STYLEGUIDE", "1") == "0":
        raise HTTPException(status_code=404)
    html = _env().get_template("styleguide.html").render(active="styleguide", **_nav_flags(store))
    return HTMLResponse(content=html)
