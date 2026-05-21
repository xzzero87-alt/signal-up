# ADR-0014: 운영 가이드 ↔ 코드 path/key 강제 동기화 정책 (CI grep 검사)

**Status:** Accepted
**Date:** 2026-05-21
**Deciders:** xzzero87-alt (사용자, crypto_trader_only 페르소나)
**Supersedes:** —
**Related:**
- ADR-0012 (`signals.jsonl` 정식화 + `STATE_SIGNALS_FILE` 상수)
- 메모리 [[feedback_contract_dead_reference]] (D+2 false alarm 3사이클 학습)
- 운영 로그 D+2 항목 [B], [B2], [B3]

## Context

운영 가이드 PowerShell 블록이 코드의 파일 경로/JSON 키와 drift할 때 false alarm 발생. D+0~D+2 시그널 프로그램에서 3사이클 false alarm 발생:

- **사이클 1 ([B], D+1):** 데일리 체크 PowerShell이 `signal_history.jsonl`을 찾는데 실파일은 `signals.jsonl`. `cli.py:280` dead reference + 운영 가이드 4곳에 동일 dead reference. → "어제 시그널 0건" 오보
- **사이클 2 ([B2], D+1 추가 진단):** D+1 시그널 0건을 실 결함으로 오해 → "알림 실패 시 jsonl 미기록 결함" 가설. 진단 1사이클 더
- **사이클 3 ([B3], D+2):** PowerShell이 top-level `.timestamp`/`.market`/`.direction` 찾는데 실 스키마는 `{signal: {market, ...}, sent_at, sent_status}` nested. → ConvertFrom-Json은 성공하지만 빈 값 출력

각 사이클마다 30분~1시간 진단 추적 비용. 운영 가이드와 코드 모두 한국어 markdown으로 자유 작성되므로 자동 동기화 안 됨. 운영 가이드 정정 시 4곳 동시 처리 필요 (운영 로그 / 운영 매뉴얼 §3.1, §5.3, §7.1, §8.4 / release_checklist §3 / 통합 핸드오프 §2.3). 하나라도 누락 시 재발.

## Decision

1. **코드 측 (ADR-0012와 결합):** 모든 path/key는 `signal_program/constants.py` 단일 모듈의 상수로 정의. 문자열 리터럴 박아두는 패턴 금지.
2. **운영 가이드 측 PowerShell 블록 변수화:**
   ```powershell
   # 표준 패턴
   $LOG_FILE = "signals.jsonl"   # ← 상수 (코드와 동일)
   $log = "C:\Users\user3\Desktop\VibeCoding\signal-up\state\$LOG_FILE"
   $yest_lines = Get-Content $log -Encoding UTF8 | Where-Object {
       $_ -match "`"sent_at`":\s*`"$yest"   # ← key 명시 (코드 스키마와 동일)
   }
   ```
3. **CI 자동 검사:** `tests/integration/test_operational_contracts.py` 추가:
   - 운영 가이드 markdown(`handoff/`) 내 jsonl 파일명 정규식 추출 → `STATE_SIGNALS_FILE` 상수와 비교
   - `signals.jsonl` 첫 줄 top-level 키 추출 → 운영 가이드 PowerShell의 `$_.<key>` 또는 `"<key>":` 정규식 패턴과 비교
   - drift 발생 시 CI RED + 정확한 drift 위치 보고
4. **PR 머지 전 강제:** GitHub Actions(또는 로컬 pre-commit) 게이트로 정정 없이는 머지 불가.
5. **PowerShell [DateTime] cast 호환 helper 표준화 ([[feedback_powershell_datetime_cast]]):**
   - 운영 가이드 PowerShell 블록 첫 부분에 `Get-DateStr` / `Get-DateOnly` helper 함수 항상 포함
   - PowerShell 5.x ↔ 7+ 양쪽 호환

## Consequences

**Positive:**
- false alarm 자동 차단 (CI 시점에 drift 감지)
- 운영 가이드 PowerShell 블록의 신뢰도 영구 유지
- 신규 핸드오프 작성 시 contract 자동 검증
- D+2 같은 진단 추적 비용 0
- 운영 매뉴얼이 코드와 함께 evolve

**Negative:**
- 운영 가이드 markdown 작성 시 정규식 규칙 학습 부담 (한 줄 패턴이라 작음)
- 운영 가이드를 자유 markdown으로 못 씀 (PowerShell 블록은 매칭 가능 형태 강제)
- CI 시간 약간 증가 (수 초)

**Trade-offs:**
- 강제 동기화 vs 자유 작성: 사용자 1인 운영 + 친구 1~2명 배포 환경에서는 강제 동기화가 가치 더 높음 (사고 추적 비용 절감)
- 신규 의존성 0 (pytest + 정규식 표준 라이브러리만 사용)

## Action Items

- ⏳ v2.1 Phase 1: `signal_program/constants.py` 추가 (ADR-0012)
- ⏳ v2.1: `tests/integration/test_operational_contracts.py` 작성 — drift 자동 검사
- ⏳ v2.1: 운영 가이드 4곳 PowerShell 블록 변수화 (D+2에 정정 완료 → v2.1에서 변수화 추가)
- ⏳ v2.1: CI 워크플로우에 통합 (이미 pytest 게이트 있으면 자동 포함)
- ⏳ v2.1: `Get-DateStr` / `Get-DateOnly` helper를 운영 가이드 표준 prelude로 정착
- ✅ D+2 학습 메모리화: [[feedback_contract_dead_reference]] + [[feedback_powershell_datetime_cast]]
