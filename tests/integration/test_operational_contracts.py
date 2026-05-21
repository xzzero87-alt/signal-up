"""운영 가이드 ↔ 코드 path/key 자동 동기화 검사 (ADR-0014).

CI 게이트: STATE_SIGNALS_FILE 상수와 실제 경로가 불일치하면 RED.
환경변수 SIGNAL_HANDOFF_DIR 설정 시 운영 가이드 markdown도 함께 검사한다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from signal_program.constants import STATE_DIR, STATE_SIGNALS_FILE


def test_state_signals_file_constant_value() -> None:
    """STATE_SIGNALS_FILE 상수가 실제 파일명과 일치해야 한다."""
    assert STATE_SIGNALS_FILE == "signals.jsonl"


def test_state_dir_constant_value() -> None:
    """STATE_DIR 상수가 'state'여야 한다."""
    assert STATE_DIR == "state"


def test_no_dead_signal_history_reference_in_src() -> None:
    """src/ 내부에 signal_history.jsonl dead reference가 없어야 한다 (ADR-0012).

    모든 코드 경로는 STATE_SIGNALS_FILE 상수를 import해 사용해야 한다.
    """
    src_root = Path(__file__).parents[2] / "src"
    dead_refs = [
        str(f)
        for f in src_root.rglob("*.py")
        if "signal_history.jsonl" in f.read_text(encoding="utf-8")
    ]
    assert not dead_refs, (
        "src/ 내 signal_history.jsonl dead reference 발견:\n" + "\n".join(dead_refs)
    )


# 운영 가이드 파일 목록 — SIGNAL_HANDOFF_DIR 미설정 시 skip
_HANDOFF_DIR = Path(
    os.environ.get(
        "SIGNAL_HANDOFF_DIR",
        str(Path(__file__).parents[2] / "handoff"),  # 통상 존재하지 않는 경로 → skip
    )
)
_MANUAL_FILES = [
    "v2.0_operation_manual_D1_to_D7.md",
    "v2.0_operation_log.md",
    "v2.0_release_checklist.md",
]


@pytest.mark.parametrize("manual_name", _MANUAL_FILES)
def test_operation_manual_signals_path_matches_constant(manual_name: str) -> None:
    """운영 가이드 내 jsonl 파일명이 STATE_SIGNALS_FILE 상수와 일치해야 한다 (ADR-0014).

    환경변수 SIGNAL_HANDOFF_DIR 미설정 시 skip.
    로컬 실행: SIGNAL_HANDOFF_DIR=C:\\Users\\user3\\Documents\\...\\handoff pytest
    """
    manual_path = _HANDOFF_DIR / manual_name
    if not manual_path.exists():
        pytest.skip(f"운영 가이드 파일 없음 (SIGNAL_HANDOFF_DIR 미설정): {manual_path}")

    content = manual_path.read_text(encoding="utf-8")
    matches = re.findall(r"state[/\\](\w+\.jsonl)", content)

    mismatches = [m for m in matches if m != STATE_SIGNALS_FILE]
    assert not mismatches, (
        f"{manual_name}: 코드 상수({STATE_SIGNALS_FILE!r})와 불일치하는 path: {mismatches}"
    )
