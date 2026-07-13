"""코인/kr/모멘텀 라이브 러너 게이트 단위 테스트 (ADR-0028 P0).

`_enabled_runners`가 게이트 판정 단일 소스이며, run/serve 양쪽 조립부가 이 목록으로
러너를 구성한다. 코인 v1 라이브는 ADR-0028로 중단 — coin_enabled=False가 기본이며
데몬 상시 기동(모멘텀) 중에도 코인 러너가 조립되지 않아야 한다.
"""

from __future__ import annotations

import logging

import pytest

from signal_program.cli import _enabled_runners, _run_async, _run_live_coro
from signal_program.config import Settings

pytestmark = pytest.mark.anyio


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "telegram_bot_token": "x",
        "telegram_chat_id": "1",
        "kis_app_key": "k",
        "kis_app_secret": "sec",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# --- test 1/2: 코인 게이트 --------------------------------------------------


def test_coin_runner_not_assembled_when_disabled() -> None:
    """coin_enabled=False → 코인 러너 미조립 (ADR-0028 핵심)."""
    active = _enabled_runners(_settings(coin_enabled=False, momentum_enabled=True))
    assert "coin" not in active


def test_coin_runner_assembled_when_enabled() -> None:
    """coin_enabled=True → 코인 러너 조립 (회귀 — 플래그 켜면 되살아나야 함)."""
    active = _enabled_runners(_settings(coin_enabled=True))
    assert "coin" in active


# --- test 3: 세 플래그 조합 -------------------------------------------------


@pytest.mark.parametrize(
    ("coin", "kr", "momentum", "expected"),
    [
        (False, False, False, []),
        (False, False, True, ["momentum"]),
        (False, True, True, ["kr", "momentum"]),
        (True, True, True, ["coin", "kr", "momentum"]),
        (True, False, False, ["coin"]),
        (True, False, True, ["coin", "momentum"]),
    ],
)
def test_enabled_runners_flag_combinations(
    coin: bool, kr: bool, momentum: bool, expected: list[str]
) -> None:
    """플래그 조합별로 조립 순서(coin→kr→momentum)대로 정확한 러너 집합."""
    active = _enabled_runners(
        _settings(coin_enabled=coin, kr_enabled=kr, momentum_enabled=momentum)
    )
    assert active == expected


def test_kr_requires_credentials() -> None:
    """kr_enabled=True라도 KIS 크리덴셜이 없으면 kr 러너 미조립."""
    active = _enabled_runners(
        _settings(kr_enabled=True, kis_app_key="", kis_app_secret="", momentum_enabled=True)
    )
    assert active == ["momentum"]


# --- test 4: 활성 러너 0 → 명시적 로그 + 정상 종료 (조용한 죽음 방지) -------


async def test_run_async_no_active_runners_logs_and_returns(
    tmp_path: object,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run 경로: 모든 플래그 off → 경고 로그 후 즉시 정상 종료(무한대기·크래시 없음).

    configure_logging은 structlog을 PrintLoggerFactory(sys.stdout)로 전역 재구성(캐시)한다.
    단위 테스트에서 실행하면 xdist 캡처 stdout에 로거가 고정돼 teardown 후 다른 테스트의
    로그가 닫힌 파일에 써지며 워커가 죽는다 → no-op으로 패치해 전역 로깅 오염 방지.
    경고는 stdlib logging(caplog)으로 확인한다.
    """
    monkeypatch.setattr("signal_program.cli.configure_logging", lambda _s: None)
    settings = _settings(
        coin_enabled=False,
        kr_enabled=False,
        momentum_enabled=False,
        signals_log_path=tmp_path / "signals.jsonl",  # type: ignore[operator]
        charts_dir=tmp_path / "charts",  # type: ignore[operator]
    )
    with caplog.at_level(logging.WARNING):
        result = await _run_async(settings)
    assert result is None
    assert any("no_live_runner_enabled" in r.message for r in caplog.records)


async def test_run_live_coro_no_active_runners_logs_and_returns(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """serve 경로: 모든 플래그 off → 경고 로그 후 정상 종료.

    RunnerHandle._supervise는 factory 정상 완료를 running=False로만 처리(재시작 없음)이라
    빈 러너 종료가 재시작 루프를 만들지 않는다.
    """
    settings = _settings(
        coin_enabled=False,
        kr_enabled=False,
        momentum_enabled=False,
        signals_log_path=tmp_path / "signals.jsonl",  # type: ignore[operator]
        charts_dir=tmp_path / "charts",  # type: ignore[operator]
    )
    with caplog.at_level(logging.WARNING):
        result = await _run_live_coro(settings)
    assert result is None
    assert any("no_live_runner_enabled" in r.message for r in caplog.records)
