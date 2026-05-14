"""GET/PUT /api/settings — 설정 조회·갱신."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from signal_program.state.settings_store import SettingsStore  # noqa: TC001
from signal_program.web.deps import get_settings_store
from signal_program.web.schemas import SettingsUpdate, SettingsView
from signal_program.web.security import friendly_validation_errors, mask_secret_value

router = APIRouter(tags=["settings"])


def _to_view(settings: object) -> SettingsView:
    from signal_program.config import Settings  # noqa: TC001

    s: Settings = settings  # type: ignore[assignment]
    return SettingsView(
        telegram_bot_token_masked=mask_secret_value(s.telegram_bot_token),
        telegram_chat_id=s.telegram_chat_id or None,
        whitelist_markets=tuple(s.whitelist_markets),
        bb_period=s.bb_period,
        bb_std_mult=s.bb_std_mult,
        cci_period=s.cci_period,
        cci_threshold_normal=s.cci_threshold_normal,
        cci_threshold_strong=s.cci_threshold_strong,
        volume_ratio_min_a=s.volume_ratio_min_a,
        volume_ratio_min_b=s.volume_ratio_min_b,
        squeeze_lookback=s.squeeze_lookback,
        squeeze_quantile=s.squeeze_quantile,
        cooldown_hours=s.cooldown_hours,
        dry_run=s.dry_run,
    )


@router.get("/api/settings", response_model=SettingsView)
def get_settings(store: SettingsStore = Depends(get_settings_store)) -> SettingsView:
    return _to_view(store.load())


@router.put("/api/settings", response_model=SettingsView)
def put_settings(
    body: SettingsUpdate,
    store: SettingsStore = Depends(get_settings_store),
) -> SettingsView:
    try:
        updated = store.update(body)
    except ValidationError as exc:
        errors = friendly_validation_errors(exc)
        raise HTTPException(status_code=422, detail=errors) from exc
    return _to_view(updated)
