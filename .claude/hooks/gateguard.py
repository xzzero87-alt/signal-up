#!/usr/bin/env python3
"""GateGuard mini — 사실 강제 PreToolUse 게이트 (Edit/Write/MultiEdit/Bash).

원리:
    Claude의 자기 평가("괜찮을까?")는 통하지 않는다.
    구체적 사실 조사("이 파일을 import하는 파일들은?")를 강제하면
    LLM은 실제 Grep/Read를 호출하게 되고, 그 조사 자체가 출력 품질을 올린다.

동작:
    - Edit/Write/MultiEdit: 파일당 첫 호출 시 차단(exit 2) + 사실 4가지 요청
    - Bash 파괴적 명령(rm -rf, git reset --hard 등): 매번 차단 + 영향 범위/롤백 요청
    - Bash 일반 명령: 세션당 1회 안내 후 통과

비활성화:
    환경변수 GATEGUARD_OFF=1 로 시작하거나, .claude/.gateguard-off 파일 존재 시 통과
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / ".claude" / ".gateguard-state.json"
OFF_MARKER = REPO_ROOT / ".claude" / ".gateguard-off"

DESTRUCTIVE_PATTERNS = (
    r"\brm\s+-rf?\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+push\s+(--force|-f)\b",
    r"\bdrop\s+table\b",
    r"\bdrop\s+database\b",
    r"\btruncate\s+table\b",
    r"\bdd\s+if=",
)


def _load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"edited_files": [], "bash_seen": False}
    return {"edited_files": [], "bash_seen": False}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_user_instruction() -> str:
    """현재 사용자 지시 추정. Claude Code가 stdin 데이터에 넣어주면 사용, 아니면 빈 문자열."""
    return os.environ.get("CLAUDE_USER_INSTRUCTION", "(미수신 — 직접 인용해 주세요)")


def _is_destructive(cmd: str) -> bool:
    return any(re.search(p, cmd, flags=re.IGNORECASE) for p in DESTRUCTIVE_PATTERNS)


def main() -> int:
    # 비활성화 옵션
    if os.environ.get("GATEGUARD_OFF") == "1" or OFF_MARKER.exists():
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # 입력이 비정상이면 통과(안전망)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name in ("Edit", "Write", "MultiEdit"):
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return 0

        state = _load_state()
        if file_path in state["edited_files"]:
            return 0  # 같은 파일 두 번째부터는 통과

        state["edited_files"].append(file_path)
        _save_state(state)

        rel = pathlib.Path(file_path).name
        msg = f"""🔒 GateGuard — {tool_name}: {file_path}

이 파일에 처음 손대기 전 다음 4가지를 먼저 보고하고 같은 도구를 다시 호출하세요.
조사 자체가 변경 품질을 올립니다. 자기 평가('이 정도면 괜찮음') 금지.

1. 이 파일을 import/require/from-import 하는 다른 파일 목록
   → Grep "{pathlib.Path(file_path).stem}" 또는 "from .*{pathlib.Path(file_path).stem}" 실행
2. 변경의 영향을 받을 public 함수/클래스 이름
   → 현 파일을 Read해서 public 시그니처 추출
3. 데이터 파일을 R/W한다면 스키마(필드명·타입·날짜 형식)
   → 실제 데이터 1~2 라인 redacted/synthetic 값으로 인용
4. 사용자 현재 지시 한 줄 인용
   → "{_read_user_instruction()}"

조사 후 같은 도구를 같은 인자로 다시 호출하면 통과합니다."""
        print(msg, file=sys.stderr)
        return 2  # 차단

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")

        if _is_destructive(cmd):
            msg = f"""🔒 GateGuard — 파괴적 Bash 명령
$ {cmd}

다음을 먼저 보고하고 같은 명령을 다시 호출하세요.
파괴적 명령은 매번 게이트를 거칩니다.

1. 이 명령이 수정/삭제할 모든 파일·데이터 목록
2. 한 줄 롤백 절차 (가능하지 않다면 그 사실을 명시)
3. 사용자 현재 지시 한 줄 인용
   → "{_read_user_instruction()}"
"""
            print(msg, file=sys.stderr)
            return 2

        state = _load_state()
        if not state["bash_seen"]:
            state["bash_seen"] = True
            _save_state(state)
            msg = f"""🔒 GateGuard — 첫 Bash 명령 (세션당 1회)
$ {cmd}

다음을 보고하고 같은 명령을 다시 호출하세요. 이후 일반 bash는 자유.

1. 사용자 현재 요청을 한 문장으로
2. 이 명령이 무엇을 검증·생산하는지
"""
            print(msg, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
