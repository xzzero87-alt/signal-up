"""serve CLI start_daemon 플래그 단위 테스트 — M16 Follow-up."""
from __future__ import annotations

import pathlib
import re


def test_serve_start_daemon_default_is_false() -> None:
    """`--start-daemon` 기본값이 False여야 한다 — 플래그 없이 실행 시 데몬 미기동."""
    src = pathlib.Path(__file__).parents[3] / "src" / "signal_program" / "cli.py"
    text = src.read_text(encoding="utf-8")
    # typer.Option 에서 start_daemon 파라미터의 기본값이 = False 임을 확인 (멀티라인)
    assert re.search(r"start_daemon.*?=\s*False", text, re.DOTALL), (
        "serve 명령의 start_daemon 기본값이 False가 아님 — 플래그 없이 데몬이 자동 시작될 수 있음"
    )


def test_serve_start_daemon_branch_checks_flag() -> None:
    """`if start_daemon:` 분기가 실제로 플래그를 검사해야 한다."""
    src = pathlib.Path(__file__).parents[3] / "src" / "signal_program" / "cli.py"
    text = src.read_text(encoding="utf-8")
    # if start_daemon: 조건 분기 + handle.start() 호출이 함께 있어야 함
    assert re.search(r"if start_daemon", text), (
        "cli.py serve: start_daemon 조건 분기 없음"
    )
    assert re.search(r"await handle\.start\(\)", text), (
        "cli.py serve: handle.start() 호출 없음"
    )


def test_serve_async_accepts_web_auth_password_parameter() -> None:
    """결함 회귀: _serve_async 시그니처에 web_auth_password 파라미터가 있어야 한다."""
    import inspect

    from signal_program import cli

    sig = inspect.signature(cli._serve_async)
    assert "web_auth_password" in sig.parameters, (
        "_serve_async에 web_auth_password 파라미터 없음 — settings.json 비번이 create_app에 전달 안 됨"
    )


def test_serve_passes_web_auth_password_to_serve_async() -> None:
    """결함 회귀: cli.py serve가 current.web_auth_password를 _serve_async에 전달해야 한다."""
    src = pathlib.Path(__file__).parents[3] / "src" / "signal_program" / "cli.py"
    text = src.read_text(encoding="utf-8")
    # _serve_async 호출 시 web_auth_password 인자 포함 여부
    assert re.search(r"_serve_async.*web_auth_password", text, re.DOTALL), (
        "cli.py serve: _serve_async 호출에 web_auth_password 인자 없음"
    )
