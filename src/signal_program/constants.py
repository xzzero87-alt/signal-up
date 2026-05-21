"""애플리케이션 전체 경로/파일명 상수 (ADR-0012).

모든 state 파일 경로는 이 모듈의 상수를 import해 사용한다.
문자열 리터럴로 직접 박아두는 패턴 금지.
"""

from __future__ import annotations

from typing import Final

#: state/ 디렉토리 이름
STATE_DIR: Final[str] = "state"

#: 시그널 이력 JSONL 파일 이름 (ADR-0012)
STATE_SIGNALS_FILE: Final[str] = "signals.jsonl"
