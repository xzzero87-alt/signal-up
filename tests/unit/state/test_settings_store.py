"""SettingsStore 단위 테스트 — Phase 1: RED."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_program.config import Settings
from signal_program.state.settings_store import SettingsStore


@pytest.fixture
def env_settings() -> Settings:
    return Settings()


@pytest.fixture
def store(tmp_path: Path, env_settings: Settings) -> SettingsStore:
    return SettingsStore(path=tmp_path / "settings.json", env_settings=env_settings)


def test_load_returns_env_settings_when_file_missing(store: SettingsStore) -> None:
    s = store.load()
    assert isinstance(s, Settings)
    assert s.bb_period == 20  # default


def test_load_returns_json_settings_when_file_exists(
    tmp_path: Path, env_settings: Settings
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"bb_period": 35}), encoding="utf-8")
    store = SettingsStore(path=path, env_settings=env_settings)
    s = store.load()
    assert s.bb_period == 35


def test_save_creates_state_settings_json(store: SettingsStore, env_settings: Settings) -> None:
    settings = env_settings.model_copy(update={"bb_period": 40})
    store.save(settings)
    assert store._path.exists()
    data = json.loads(store._path.read_text(encoding="utf-8"))
    assert data["bb_period"] == 40


def test_update_applies_patch_and_persists(store: SettingsStore) -> None:
    from signal_program.web.schemas import SettingsUpdate

    patch = SettingsUpdate(bb_period=45)
    updated = store.update(patch)
    assert updated.bb_period == 45
    assert store._path.exists()


def test_update_rejects_invalid_constraint(store: SettingsStore) -> None:
    from pydantic import ValidationError
    from signal_program.web.schemas import SettingsUpdate

    with pytest.raises((ValidationError, ValueError)):
        SettingsUpdate(bb_period=0)  # ge=2 위반
