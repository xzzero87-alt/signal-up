"""GET /api/dashboard — 통합 대시보드 데이터."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from signal_program.state.settings_store import SettingsStore  # noqa: TC001
from signal_program.web.api.signals import recent_signals
from signal_program.web.deps import get_settings_store
from signal_program.web.schemas import DashboardView

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard", response_model=DashboardView)
def dashboard_view(
    request: Request,
    store: SettingsStore = Depends(get_settings_store),
) -> DashboardView:
    s = store.load()
    signals = recent_signals(limit=50)

    settings_summary: dict[str, object] = {
        "dry_run": s.dry_run,
        "bb_std_mult": s.bb_std_mult,
        "cooldown_hours": s.cooldown_hours,
        "whitelist_count": len(s.whitelist_markets),
        # 상태 패널용 (M20 대시보드 재설계)
        "strategy_version": s.strategy_version,
        "bb_period": s.bb_period,
        "cci_threshold_normal": s.cci_threshold_normal,
        "cci_threshold_strong": s.cci_threshold_strong,
        # 운용 현황 목록: 어떤 마켓이 어떤 전략으로 실행 중인지
        "whitelist_markets": list(s.whitelist_markets),
        "kr_enabled": s.kr_enabled,
        "kr_strategy": s.kr_strategy,
        "kr_whitelist_symbols": list(s.kr_whitelist_symbols),
        "ai_enrichment_enabled": s.ai_enrichment_enabled,
    }

    handle = getattr(request.app.state, "runner_handle", None)
    daemon_running = False
    started_at = None
    last_signal_at = None
    if handle is not None:
        st = handle.status()
        daemon_running = st.running
        started_at = st.started_at
        last_signal_at = st.last_signal_at
    settings_summary["daemon_started_at"] = started_at.isoformat() if started_at else None
    settings_summary["last_signal_at"] = last_signal_at.isoformat() if last_signal_at else None

    return DashboardView(
        daemon_status="running" if daemon_running else "stopped",
        next_evaluation_at=None,
        recent_signals=list(signals),  # type: ignore[arg-type]
        settings_summary=settings_summary,
    )
