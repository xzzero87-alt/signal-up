"""애플리케이션 설정 — pydantic-settings 기반.

로드 우선순위 (ADR-0008):
1. state/settings.json 존재 시 JSON 로드  (마일스톤 13 이후)
2. state/settings.json 미존재 시 .env 로드 (부트스트랩)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

_DEFAULT_WHITELIST: list[str] = [
    "KRW-BTC",
    "KRW-ETH",
    "KRW-SOL",
    "KRW-XRP",
    "KRW-ADA",
    "KRW-DOGE",
    "KRW-AVAX",
    "KRW-LINK",
    "KRW-DOT",
    "KRW-BCH",
    "KRW-TRX",
    "KRW-ATOM",
    "KRW-NEAR",
    "KRW-UNI",
    "KRW-APT",
    "KRW-ARB",
    "KRW-OP",
    "KRW-NEO",
    "KRW-SHIB",
]

# 쉼표 구분 파싱을 적용할 필드
_COMMA_FIELDS: frozenset[str] = frozenset({"whitelist_markets"})


class _CommaAwareEnvSource(EnvSettingsSource):
    """쉼표 구분 환경변수를 list[str]로 파싱하는 커스텀 소스."""

    def decode_complex_value(self, field_name: str, field: FieldInfo, value: Any) -> Any:
        if (
            field_name in _COMMA_FIELDS
            and isinstance(value, str)
            and not value.strip().startswith("[")
        ):
            return [item.strip() for item in value.split(",") if item.strip()]
        return json.loads(value)


class _CommaAwareDotEnvSource(DotEnvSettingsSource):
    """쉼표 구분 .env 파일 값을 list[str]로 파싱하는 커스텀 소스."""

    def decode_complex_value(self, field_name: str, field: FieldInfo, value: Any) -> Any:
        if (
            field_name in _COMMA_FIELDS
            and isinstance(value, str)
            and not value.strip().startswith("[")
        ):
            return [item.strip() for item in value.split(",") if item.strip()]
        return json.loads(value)


class Settings(BaseSettings):
    """애플리케이션 전체 설정. .env 또는 환경변수에서 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 텔레그램
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 화이트리스트
    whitelist_markets: list[str] = _DEFAULT_WHITELIST

    # 전략 파라미터
    bb_period: int = 20
    bb_std_mult: float = 2.0
    cci_period: int = 20
    cci_threshold_normal: int = 100
    cci_threshold_strong: int = 200
    volume_ratio_min_a: float = 1.0
    volume_ratio_min_b: float = 1.5
    squeeze_lookback: int = 120
    squeeze_quantile: float = 0.20

    # 송출 정책
    cooldown_hours: int = 2

    # 러너 스케줄
    cycle_delay_seconds: int = 30
    cycle_timeout_seconds: int = 120
    signals_log_path: Path = Path("state/signals.jsonl")
    charts_dir: Path = Path("state/charts")

    # 운영
    log_level: str = "INFO"
    dry_run: bool = False

    # 웹 대시보드 (v2.0)
    web_bind: str = "127.0.0.1"
    web_port: int = 8765
    web_auth_password: str = ""

    @field_validator("whitelist_markets", mode="before")
    @classmethod
    def _parse_whitelist(cls, v: object) -> list[str]:
        """직접 인스턴스화 시 쉼표 구분 문자열을 리스트로 변환한다."""
        if isinstance(v, str):
            return [m.strip() for m in v.split(",") if m.strip()]
        if isinstance(v, (list, tuple)):
            result = [str(item) for item in v]
            if not result:
                raise ValueError("화이트리스트는 최소 1개 마켓이 필요합니다")
            return result
        raise ValueError(f"화이트리스트를 파싱할 수 없음: {type(v).__name__}")  # noqa: EM102

    def model_post_init(self, __context: Any) -> None:
        """비-localhost 바인드 + 빈 비밀번호 조합을 거부한다 (DESIGN.md §10)."""
        if self.web_bind != "127.0.0.1" and not self.web_auth_password:
            raise SystemExit(
                "WEB_BIND가 비-localhost인데 WEB_AUTH_PASSWORD가 설정되지 않았습니다. "
                "외부 노출 시 비밀번호 필수."
            )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """쉼표 구분 리스트를 지원하는 커스텀 소스를 주입한다."""
        env_file = cls.model_config.get("env_file")
        encoding = cls.model_config.get("env_file_encoding")
        return (
            init_settings,
            _CommaAwareEnvSource(settings_cls),
            _CommaAwareDotEnvSource(
                settings_cls,
                env_file=env_file,
                env_file_encoding=encoding,
            ),
            file_secret_settings,
        )
