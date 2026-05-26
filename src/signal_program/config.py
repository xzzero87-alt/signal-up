"""애플리케이션 설정 — pydantic-settings 기반.

로드 우선순위 (ADR-0008):
1. state/settings.json 존재 시 JSON 로드  (마일스톤 13 이후)
2. state/settings.json 미존재 시 .env 로드 (부트스트랩)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from signal_program.constants import STATE_DIR, STATE_SIGNALS_FILE

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
_COMMA_FIELDS: frozenset[str] = frozenset({"whitelist_markets", "kr_whitelist_symbols"})


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
    signals_log_path: Path = Path(STATE_DIR) / STATE_SIGNALS_FILE
    charts_dir: Path = Path("state/charts")

    # V2 전략 (ADR-0010)
    strategy_version: Literal["v1", "v2"] = "v1"
    # 가중치 (합 = 1.00)
    bb_weight: float = 0.20
    cci_weight: float = 0.20
    sto_weight: float = 0.20
    obv_weight: float = 0.40
    # 발사 임계값
    buy_threshold: float = 0.65
    sell_threshold: float = 0.65
    # 스토캐스틱 임계값 (ADR-0010 §3: 15/85 엄격)
    sto_oversold: int = 15
    sto_overbought: int = 85
    # OBV 이동평균 기간
    obv_lookback: int = 20

    # KIS Open API -- 국장 (ADR-0016)
    # 키 미설정 시 KR 기능은 비활성화. 모의투자 서버 기본값(안전).
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_is_paper: bool = True
    kr_enabled: bool = False
    kr_whitelist_symbols: list[str] = []
    kr_cooldown_hours_60m: int = 2
    kr_cooldown_hours_120m: int = 4

    # 운영
    log_level: str = "INFO"
    dry_run: bool = False

    # 웹 대시보드 (v2.0)
    web_bind: str = "127.0.0.1"
    web_port: int = 8765
    web_auth_password: str = ""

    @field_validator("kr_whitelist_symbols", mode="before")
    @classmethod
    def _parse_kr_symbols(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, (list, tuple)):
            return [str(item) for item in v]
        raise ValueError(f"kr_whitelist_symbols parse error: {type(v).__name__}")  # noqa: EM102

    @field_validator("whitelist_markets", mode="before")
    @classmethod
    def _parse_whitelist(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [m.strip() for m in v.split(",") if m.strip()]
        if isinstance(v, (list, tuple)):
            result = [str(item) for item in v]
            if not result:
                raise ValueError("화이트리스트는 마켓이 하나 이상 필요합니다")
            return result
        raise ValueError(f"whitelist_markets parse error: {type(v).__name__}")  # noqa: EM102

    def model_post_init(self, __context: Any) -> None:
        if self.web_bind != "127.0.0.1" and not self.web_auth_password:
            raise SystemExit(
                "WEB_BIND is non-localhost but WEB_AUTH_PASSWORD is not set. "
                "Password required for external exposure."
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
