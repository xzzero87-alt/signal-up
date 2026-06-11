"""Settings 유닛 테스트 (마일스톤 1)."""

import pytest
from pydantic import ValidationError

from signal_program.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.bb_period == 20
    assert settings.cci_period == 20
    assert settings.bb_std_mult == 2.0
    assert settings.web_bind == "127.0.0.1"
    assert settings.web_port == 8765
    assert settings.dry_run is False
    assert settings.cooldown_hours == 2
    assert len(settings.whitelist_markets) == 19


def test_whitelist_parse_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHITELIST_MARKETS", "KRW-BTC,KRW-ETH, KRW-SOL ")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.whitelist_markets == ["KRW-BTC", "KRW-ETH", "KRW-SOL"]


def test_whitelist_default_has_expected_markets() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    for market in ("KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-SHIB"):
        assert market in settings.whitelist_markets
    assert "KRW-LTC" not in settings.whitelist_markets


def test_empty_coin_whitelist_allowed_with_kr_symbols() -> None:
    """v2.2 M2: 코인 화이트리스트가 비어도 국장 종목이 있으면 허용."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        whitelist_markets=[],
        kr_whitelist_symbols=["005930"],
    )
    assert settings.whitelist_markets == []
    assert settings.kr_whitelist_symbols == ["005930"]


def test_both_empty_whitelists_rejected() -> None:
    """v2.2 M2: 코인·국장 둘 다 비면 거부."""
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            whitelist_markets=[],
            kr_whitelist_symbols=[],
        )


def test_web_bind_guard_raises_on_missing_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_BIND", "0.0.0.0")
    monkeypatch.setenv("WEB_AUTH_PASSWORD", "")
    with pytest.raises(SystemExit):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_web_bind_with_password_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_BIND", "0.0.0.0")
    monkeypatch.setenv("WEB_AUTH_PASSWORD", "strong-secret")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.web_bind == "0.0.0.0"
    assert settings.web_auth_password == "strong-secret"


def test_ai_enrichment_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.ai_enrichment_enabled is False
    assert settings.anthropic_api_key == ""
    assert settings.ai_enrichment_model == "claude-haiku-4-5"
    assert settings.ai_enrichment_daily_cap == 30
    assert settings.ai_enrichment_timeout_seconds == 25


def test_ai_enrichment_cap_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_enrichment_daily_cap=0)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_enrichment_daily_cap=501)  # type: ignore[call-arg]
