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


def test_load_resilient_to_utf8_bom(tmp_path: Path, env_settings: Settings) -> None:
    """결함 회귀: PS5.x Set-Content -Encoding utf8 는 BOM 추가 — 로드 실패 없어야 한다."""
    path = tmp_path / "settings.json"
    bom = b"\xef\xbb\xbf"
    content = json.dumps({"web_auth_password": "test1234567890ab"}).encode("utf-8")
    path.write_bytes(bom + content)

    store = SettingsStore(path=path, env_settings=env_settings)
    loaded = store.load()
    assert loaded.web_auth_password == "test1234567890ab", (
        "BOM이 포함된 settings.json 로드 실패 — PS5.x 호환성 결함"
    )
