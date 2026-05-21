# ADR-0012: `signals.jsonl` 영속 파일 정식화 + `STATE_SIGNALS_FILE` 상수

**Status:** Accepted
**Date:** 2026-05-21
**Deciders:** xzzero87-alt (사용자, crypto_trader_only 페르소나)
**Supersedes:** —
**Related:**
- ADR-0008 (settings.json single source of truth)
- ADR-0014 (운영 가이드 ↔ 코드 path 강제 동기화)
- 운영 로그 D+2 항목 [B], `cli.py:280` dead reference
- `..\..\handoff\v2.1.0_strategy_v2.md` §2 (v2.0.4 핫픽스)

## Context

v2.0.0 출시 후 데몬이 시그널 이력을 영속화하는 파일은 실제로 `state/signals.jsonl`로 자리잡았다. 그러나 `cli.py:280`이 `Path("state/signal_history.jsonl")`로 작성되어 있었고, 운영 가이드 PowerShell 4곳(`v2.0_operation_log.md` line 322, `v2.0_operation_manual_D1_to_D7.md` §3.1/§5.3/§7.1, `v2.0_release_checklist.md` §3)도 같은 dead reference를 박아두고 있었다.

D+0~D+2 운영 중 false alarm 3사이클이 발생했다. 데일리 체크 PowerShell이 `signal_history.jsonl`을 찾아 "시그널 0건" 출력 → 실 결함으로 오해 → 가설 추적에 시간 낭비. 세 번째 사이클에서야 실파일이 `signals.jsonl`이고 스키마는 nested(`{signal: {market, ...}, sent_at, sent_status}`)임이 확정.

## Decision

1. **정식 파일명:** `state/signals.jsonl` 단일.
2. **코드 상수화:** `signal_program/constants.py`에 다음 상수 정의:
   ```python
   from typing import Final
   STATE_SIGNALS_FILE: Final[str] = "signals.jsonl"
   STATE_DIR: Final[str] = "state"
   ```
3. **호출부 일괄 import:** `cli.py`, `web/api/signals.py`, `state/signal_history.py` 등 모든 호출부가 위 상수를 import. 문자열 리터럴 박아두는 패턴 금지.
4. **운영 가이드 PowerShell:** 같은 경로 명시(`signals.jsonl`). 향후 ADR-0014와 결합해 CI에서 자동 동기화 검증.
5. **`signal_history.jsonl` 처리:** 파일 자체는 존재하지 않으므로 코드 dead reference 제거만으로 충분. signals.jsonl rename 금지 (D+0~D+2 적재된 43건 baseline 데이터 보존).

## Consequences

**Positive:**
- false alarm 회피 (스키마와 path 양쪽 일치 확정)
- ADR-0014와 결합 시 CI grep으로 drift 자동 감지
- 신규 호출부 추가 시 상수 import 패턴 강제
- D+2 누적 43건 baseline 데이터 보존 (rename X)

**Negative:**
- `signal_program/constants.py` 신규 모듈 (작은 비용)
- 기존 호출부 import 추가 작업 (v2.1 진입 시 일괄 처리)

## Action Items

- ✅ v2.0.4 commit `3e64987`에서 `cli.py:280` + `web/api/signals.py:4` docstring + `.claude/CLAUDE.md:35` 정정 완료
- ⏳ v2.1 Phase 1: `signal_program/constants.py` 신규 추가 + 호출부 import 일괄 처리
- ⏳ v2.1: ADR-0014와 결합한 CI grep 검사 추가 (`tests/integration/test_operational_contracts.py`)
- ✅ 운영 가이드 4곳 PowerShell 정정 (D+2, v2.0.4 이전 사전 정리)
