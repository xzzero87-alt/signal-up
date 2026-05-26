"""Web API 요청/응답 Pydantic 스키마 — DESIGN.md §8.6.

SettingsView: GET 응답 (시크릿 마스킹)
SettingsUpdate: PUT 요청 (부분 업데이트, None = 미변경)

Note: DESIGN §8.6 SettingsUpdate는 전체 필드 필수였으나 M14 "비워두면 기존 값 유지" 요구로
partial-update 형태로 구현. 구현 현실을 §8.7로 추가 예정.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SettingsView(BaseModel):
    """GET 응답. 시크릿 필드는 마스킹된 문자열."""

    model_config = ConfigDict(extra="forbid")

    telegram_bot_token_masked: str
    telegram_chat_id: str | None
    whitelist_markets: tuple[str, ...]
    bb_period: int = Field(ge=2, le=200)
    bb_std_mult: float = Field(gt=0, le=5)
    cci_period: int = Field(ge=2, le=200)
    cci_threshold_normal: int = Field(ge=50, le=500)
    cci_threshold_strong: int = Field(ge=50, le=1000)
    volume_ratio_min_a: float = Field(ge=0)
    volume_ratio_min_b: float = Field(ge=0)
    squeeze_lookback: int = Field(ge=20, le=500)
    squeeze_quantile: float = Field(gt=0, lt=1)
    cooldown_hours: int = Field(ge=0, le=72)
    dry_run: bool
    # V2 전략 필드 (ADR-0010)
    strategy_version: Literal["v1", "v2"] = "v1"
    bb_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    cci_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    sto_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    obv_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    buy_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    sell_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    sto_oversold: int = Field(default=15, ge=1, le=50)
    sto_overbought: int = Field(default=85, ge=50, le=99)


class SettingsUpdate(BaseModel):
    """PUT 요청. 부분 업데이트 — None이면 해당 필드 변경 안 함."""

    model_config = ConfigDict(extra="forbid")

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    whitelist_markets: list[str] | None = None
    bb_period: int | None = Field(default=None, ge=2, le=200)
    bb_std_mult: float | None = Field(default=None, gt=0, le=5)
    cci_period: int | None = Field(default=None, ge=2, le=200)
    cci_threshold_normal: int | None = Field(default=None, ge=50, le=500)
    cci_threshold_strong: int | None = Field(default=None, ge=50, le=1000)
    volume_ratio_min_a: float | None = Field(default=None, ge=0)
    volume_ratio_min_b: float | None = Field(default=None, ge=0)
    squeeze_lookback: int | None = Field(default=None, ge=20, le=500)
    squeeze_quantile: float | None = Field(default=None, gt=0, lt=1)
    cooldown_hours: int | None = Field(default=None, ge=0, le=72)
    dry_run: bool | None = None
    # V2 전략 필드 (ADR-0010) — None이면 변경 안 함
    strategy_version: Literal["v1", "v2"] | None = None
    bb_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    cci_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    sto_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    obv_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    buy_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    sell_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    sto_oversold: int | None = Field(default=None, ge=1, le=50)
    sto_overbought: int | None = Field(default=None, ge=50, le=99)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    version: str


class BacktestJobSubmit(BaseModel):
    """POST /api/backtest/jobs 요청 바디."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["backtest", "walkforward"] = "backtest"
    market: str
    period_from: date
    period_to: date
    mode: Literal["A", "B", "both"] = "both"
    train_months: int | None = Field(default=None, ge=1, le=24)
    validate_months: int | None = Field(default=None, ge=1, le=12)
    grid_str: str | None = None

    @model_validator(mode="after")
    def check_period(self) -> BacktestJobSubmit:
        if self.period_to <= self.period_from:
            raise ValueError("period_to는 period_from 이후여야 합니다")
        return self


class JobView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    kind: str = "backtest"
    status: Literal["queued", "running", "succeeded", "failed"]
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    market: str
    period_from: str
    period_to: str
    result_path: str | None = None
    error_message: str | None = None


class DaemonStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    running: bool
    started_at: datetime | None = None
    last_signal_at: datetime | None = None
    next_poll_at: datetime | None = None


class DashboardView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daemon_status: str
    next_evaluation_at: datetime | None = None
    recent_signals: list[dict[str, object]] = Field(default_factory=list)
    settings_summary: dict[str, object] = Field(default_factory=dict)


class SignalCardEntry(BaseModel):
    """대시보드 카드 렌더용 DTO (R_P1_9).

    Signal 도메인 모델을 확장하지 않고 래핑한다.
    """

    model_config = ConfigDict(extra="forbid")

    signal_id: str  # "{triggered_at_iso}_{market}"
    market: str
    triggered_at: datetime
    mode: str  # "V1" | "V2"
    direction: str  # "buy" | "sell"
    strength: str  # "normal" | "strong"
    price: float
    bb_pct_b: float
    cci: float
    volume_ratio: float
    sparkline_prices: tuple[float, ...] | None = None  # 최대 14개 close 가격
    feedback: str | None = None  # "helpful" | "confusing" | "bad" | None


class FeedbackStats(BaseModel):
    """거짓신호율 집계 결과. GET /api/signals/stats 응답 (R_P1_14)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bad_count: int = Field(ge=0, description="'bad' 레코드 수")
    total_count: int = Field(ge=0, description="집계 대상 레코드 수")
    bad_rate: float = Field(ge=0.0, le=100.0, description="거짓신호율 (0~100%)")
    window: int = Field(ge=1, description="집계 window 크기")
    has_data: bool = Field(description="표시 가능 최소 표본 충족 여부 (total_count >= 3)")
