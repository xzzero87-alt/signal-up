"""CooldownStore — DESIGN.md §5.2 쿨다운 정책 구현.

키: (market, mode, direction) — 동일 조합 2시간 내 1회만 허용.
저장: state/cooldown.json {"<market>|<mode>|<direction>": "<iso8601_kst>"}
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from signal_program.enums import SignalDirection, StrategyMode


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
        raise NotImplementedError

    def is_cooled_down(self, key: CooldownKey, now: datetime) -> bool:
        """True 반환 시 해당 시그널 아직 쿨다운 중(송출 억제)."""
        raise NotImplementedError

    def mark_sent(self, key: CooldownKey, now: datetime) -> None:
        """송출 완료 기록 — 메모리 갱신 후 디스크에 atomic write."""
        raise NotImplementedError

    def reload(self) -> None:
        """디스크에서 상태 재로드."""
        raise NotImplementedError
