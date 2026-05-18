"""SettingsStore — state/settings.json 영속화 (ADR-0008 부팅 시퀀스).

부팅 시퀀스:
  1. state/settings.json 존재 → JSON 로드 (Settings.model_validate)
  2. 미존재 → .env 로드 Settings 반환 (직렬화 X)
  3. PUT /api/settings → 첫 save() 호출 시 settings.json 생성

import 사용처:
  - web/deps.py (get_settings_store)
  - cli.py serve 커맨드
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path  # noqa: TC003
from typing import Any

from signal_program.config import Settings


class SettingsStore:
    """ADR-0008: settings.json 단일 source of truth."""

    def __init__(self, path: Path, env_settings: Settings) -> None:
        self._path = path
        self._env_settings = env_settings

    def load(self) -> Settings:
        """파일 우선, 미존재 시 env_settings 반환."""
        if not self._path.exists():
            return self._env_settings

        try:
            data: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8-sig"))
            base = self._env_settings.model_dump()
            base.update(data)
            return Settings.model_validate(base)
        except Exception:
            return self._env_settings

    def save(self, settings: Settings) -> None:
        """state/settings.json에 저장. 부모 디렉토리 자동 생성."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = settings.model_dump(mode="json")
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if platform.system() != "Windows":
            os.chmod(self._path, 0o600)

    def update(self, patch: Any) -> Settings:
        """현재 settings에 patch(SettingsUpdate) 적용 → save → 반환."""
        current = self.load()
        patch_data = patch.model_dump(exclude_none=True)
        updated_data = current.model_dump(mode="json")
        updated_data.update(patch_data)
        updated = Settings.model_validate(updated_data)
        self.save(updated)
        return updated
