"""GET /api/dashboard — 통합 대시보드 데이터."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from signal_program.state.settings_store import SettingsStore  # noqa: TC001
from signal_program.web.api.signals import recent_signals
from signal_program.web.deps import get_settings_store
from signal_program.web.schemas import DashboardView

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard", response_model=DashboardView)
def dashboard_view(store: SettingsStore = Depends(get_settings_store)) -> DashboardView:
    s = store.load()
    signals = recent_signals(limit=50)

    settings_summary: dict[str, object] = {
        "dry_run": s.dry_run,
        "bb_std_mult": s.bb_std_mult,
        "cooldown_hours": s.cooldown_hours,
        "whitelist_count": len(s.whitelist_markets),
    }

    return DashboardView(
        daemon_status="stopped",
        next_evaluation_at=None,
        recent_signals=list(signals),  # type: ignore[arg-type]
        settings_summary=settings_summary,
    )
