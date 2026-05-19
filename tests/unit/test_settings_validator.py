"""Settings.whitelist_markets validator 단위 테스트 — Phase 2: RED.

결함 (v2.0.1): SettingsUpdate가 JSON list를 tuple로 coerce하면
Settings._parse_whitelist가 tuple을 거부하여 422 에러 발생.

커버: list/tuple/str 허용, 빈 목록 거부, 한국어 에러 메시지 검증.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from signal_program.config import Settings


def test_accepts_list_input() -> None:
    """list[str] 입력을 정상 수용해야 한다."""
    s = Settings(whitelist_markets=["KRW-BTC", "KRW-ETH"])
    assert s.whitelist_markets == ["KRW-BTC", "KRW-ETH"]


def test_accepts_tuple_input() -> None:
    """tuple 입력을 정상 수용해야 한다 (SettingsUpdate coerce 경로)."""
    s = Settings(whitelist_markets=("KRW-BTC", "KRW-SOL"))
    assert s.whitelist_markets == ["KRW-BTC", "KRW-SOL"]


def test_accepts_comma_string_input() -> None:
    """쉼표 구분 문자열은 split하여 list 반환해야 한다."""
    s = Settings(whitelist_markets="KRW-BTC, KRW-ETH , KRW-SOL")
    assert s.whitelist_markets == ["KRW-BTC", "KRW-ETH", "KRW-SOL"]


def test_rejects_empty_list() -> None:
    """빈 목록은 ValidationError를 발생시켜야 한다."""
    with pytest.raises(ValidationError):
        Settings(whitelist_markets=[])


def test_empty_list_error_message_is_korean() -> None:
    """빈 목록 에러 메시지에 한국어가 포함되어야 한다."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(whitelist_markets=[])
    errors = exc_info.value.errors()
    assert errors, "ValidationError에 에러 항목이 없음"
    msgs = " ".join(str(e.get("msg", "")) for e in errors)
    assert "화이트리스트" in msgs, f"한국어 메시지 없음: {msgs}"


def test_empty_tuple_rejected() -> None:
    """빈 tuple도 거부해야 한다."""
    with pytest.raises(ValidationError):
        Settings(whitelist_markets=())
