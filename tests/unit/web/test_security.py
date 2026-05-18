"""security.py — assert_safe_bind + mask 단위 테스트 (M16 Follow-up v4)."""

from __future__ import annotations

import pytest


def test_assert_safe_bind_accepts_password_from_arg_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENV 미설정 상태에서 password 인자만으로 통과되어야 한다."""
    monkeypatch.delenv("WEB_AUTH_PASSWORD", raising=False)
    from signal_program.web.security import assert_safe_bind

    assert_safe_bind("0.0.0.0", "secret123")  # SystemExit 없어야 함


def test_assert_safe_bind_rejects_when_password_arg_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """password 인자 None → SystemExit."""
    monkeypatch.delenv("WEB_AUTH_PASSWORD", raising=False)
    from signal_program.web.security import assert_safe_bind

    with pytest.raises(SystemExit):
        assert_safe_bind("0.0.0.0", None)


def test_assert_safe_bind_rejects_when_password_arg_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """password 인자 '' → SystemExit."""
    monkeypatch.delenv("WEB_AUTH_PASSWORD", raising=False)
    from signal_program.web.security import assert_safe_bind

    with pytest.raises(SystemExit):
        assert_safe_bind("0.0.0.0", "")


def test_assert_safe_bind_does_not_read_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    """os.environ.get를 우회하지 않음 — ENV에 값 있어도 password 인자가 빈 경우 거부."""
    monkeypatch.setenv("WEB_AUTH_PASSWORD", "from-env-should-be-ignored")
    from signal_program.web.security import assert_safe_bind

    with pytest.raises(SystemExit):
        assert_safe_bind("0.0.0.0", "")  # ENV에 값 있어도 인자가 비면 거부


def test_assert_safe_bind_passes_localhost_without_password() -> None:
    """localhost bind는 password 없어도 통과."""
    from signal_program.web.security import assert_safe_bind

    assert_safe_bind("127.0.0.1", "")
    assert_safe_bind("127.0.0.1", None)


def test_assert_safe_bind_passes_external_bind_with_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """비-localhost bind + password 있음 → 통과."""
    monkeypatch.delenv("WEB_AUTH_PASSWORD", raising=False)
    from signal_program.web.security import assert_safe_bind

    assert_safe_bind("0.0.0.0", "my-secure-password")
