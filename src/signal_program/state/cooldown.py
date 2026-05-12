"""CooldownStore — DESIGN.md §5.2 쿨다운 정책 구현.

키: (market, mode, direction) — 동일 조합 cooldown 이내 재송출 억제.
저장: JSON {"<market>|<mode>|<direction>": "<iso8601_kst>"}
"""

from __future__ import annotations

import json
import os
import platform
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import pathlib

from signal_program.enums import SignalDirection, StrategyMode

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class CooldownKey:
    """쿨다운 판정 키 — (시장, 전략 모드, 매수/매도 방향) 조합."""

    market: str
    mode: StrategyMode
    direction: SignalDirection


class CooldownStore:
    """메모리 + JSON 파일 영속 기반 쿨다운 상태 관리.

    DESIGN.md §5.2: 키=(market, mode, direction), 값=마지막 송출 timestamp.
    """

    def __init__(self, path: pathlib.Path, cooldown: timedelta) -> None:
        self._path = path
        self._cooldown = cooldown
        self._cache: dict[CooldownKey, datetime] = {}
        self._lock = threading.Lock()
        self._load_from_disk()

    def is_cooled_down(self, key: CooldownKey, now: datetime) -> bool:
        """True 반환 시 해당 시그널 아직 쿨다운 중(송출 억제)."""
        last = self._cache.get(key)
        if last is None:
            return False
        return now - last < self._cooldown

    def mark_sent(self, key: CooldownKey, now: datetime) -> None:
        """송출 완료 기록 — 메모리 갱신 후 디스크에 atomic write (thread-safe)."""
        with self._lock:
            self._cache[key] = now
            self._save_to_disk()

    def reload(self) -> None:
        """디스크에서 상태 재로드."""
        self._load_from_disk()

    # ── 내부 직렬화 ──────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_key(key: CooldownKey) -> str:
        return f"{key.market}|{key.mode.value}|{key.direction.value}"

    @staticmethod
    def _deserialize_key(s: str) -> CooldownKey:
        market, mode_val, dir_val = s.split("|", 2)
        return CooldownKey(
            market=market,
            mode=StrategyMode(mode_val),
            direction=SignalDirection(dir_val),
        )

    # ── 디스크 I/O ───────────────────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            self._cache = {}
            return
        try:
            text = self._path.read_text(encoding="utf-8").strip()
            if not text:
                self._cache = {}
                return
            data: dict[str, str] = json.loads(text)
            self._cache = {
                self._deserialize_key(k): datetime.fromisoformat(v) for k, v in data.items()
            }
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            log.warning("cooldown.load_failed", path=str(self._path), error=str(exc))
            self._cache = {}

    def _save_to_disk(self) -> None:
        data = {self._serialize_key(k): v.isoformat() for k, v in self._cache.items()}
        content = json.dumps(data, ensure_ascii=False, indent=2)
        if platform.system() == "Windows":
            # Windows: AV 스캐너 잠금 회피를 위해 직접 쓰기 (단일 사용자 앱)
            self._path.write_text(content, encoding="utf-8")
        else:
            # Unix: UUID tmp 파일로 atomic write 후 replace
            tmp = self._path.parent / f".{self._path.stem}_{uuid.uuid4().hex}.tmp"
            tmp.write_text(content, encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
            os.chmod(self._path, 0o600)
