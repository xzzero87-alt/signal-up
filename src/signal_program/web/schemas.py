"""Web API 요청/응답 Pydantic 스키마 — DESIGN.md §8.6.

SettingsView: GET 응답 (시크릿 마스킹)
SettingsUpdate: PUT 요청 (부분 업데이트, None = 미변경)

Note: DESIGN §8.6 SettingsUpdate는 전체 필드 필수였으나 M14 "비워두면 기존 값 유지" 요구로
partial-update 형태로 구현. 구현 현실을 §8.7로 추가 예정.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class SettingsUpdate(BaseModel):
    """PUT 요청. 부분 업데이트 — None이면 해당 필드 변경 안 함."""

    model_config = ConfigDict(extra="forbid")

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    whitelist_markets: tuple[str, ...] | None = None
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


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    version: str


class JobView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    submitted_at: datetime
    market: str
    period_from: str
    period_to: str


class DaemonStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    running: bool
    started_at: datetime | None = None


class DashboardView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daemon_status: str
    next_evaluation_at: datetime | None = None
    recent_signals: list[dict[str, object]] = Field(default_factory=list)
    settings_summary: dict[str, object] = Field(default_factory=dict)
