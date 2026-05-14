"""FastAPI 의존성 주입 헬퍼."""

from __future__ import annotations

from pathlib import Path

from signal_program.config import Settings
from signal_program.state.settings_store import SettingsStore

_store: SettingsStore | None = None


def init_settings_store(path: Path, env_settings: Settings) -> None:
    """앱 기동 시 한 번 호출. 전역 store 초기화."""
    global _store  # noqa: PLW0603
    _store = SettingsStore(path=path, env_settings=env_settings)


def get_settings_store() -> SettingsStore:
    """FastAPI Depends 헬퍼."""
    if _store is None:
        env = Settings()
        return SettingsStore(path=Path("state/settings.json"), env_settings=env)
    return _store
