# ADR-0013: 데몬 stdout/stderr 파일 리다이렉트 + 일별 로테이션 (Python RotatingFileHandler)

**Status:** Accepted
**Date:** 2026-05-21
**Deciders:** xzzero87-alt (사용자, crypto_trader_only 페르소나)
**Supersedes:** —
**Superseded by:** (ADR-0011 nssm 도입 시점에 재검토 — 본문 Action Items 참조)
**Related:**
- ADR-0011 (Windows Service nssm 채택)
- 운영 로그 D+0~D+2 silent restart 3회 ([A])
- D+2 신규 발견 [E] *.log 0건, [E2] uv.exe 결함, [E3] cp949 stdout

## Context

v2.0 데몬 cmdline `signal serve --start-daemon --bind 127.0.0.1`이 stdout/stderr 리다이렉트 없음. 프로젝트 전체 `*.log` 파일 0건 (`.claude\checkpoints.log` 제외).

D+0~D+2 silent restart 3회 발생, 모두 사유 추적 불가:
- D+0 13:40 PID 2300 → ~83분 후 silent death → 15:07 PID 51672 → ~32분 후 daily_check 감지 → 15:41 PID 3160
- D+1 ~18:04 PID 11564 → 55784 (사유 불명)
- D+2 09:08 PID 55784 → 첫 우회 PowerShell `$uvExe` 결함으로 5분 운영 중단 → signal.exe 직접 호출로 09:14 PID 53888 복구

D+2 [E] PowerShell 우회 (`Start-Process -WindowStyle Hidden -RedirectStandardOutput/Error`)로 `logs/daemon_stdout_*.log`에 임시 기록 시작. 단 운영자 수동 작업이고, `signal serve --start-daemon` 한 줄로 끝나야 할 운영이 PowerShell 한 블록으로 복잡해짐.

ADR-0011 (Windows Service nssm)이 프로세스 라이프사이클 + stdout/stderr 캡처 양쪽을 근본 해결하나, nssm 설치 + 사용자 교육 부담 + Phase 2 트랙(v2.1-e ★★★). v2.1 Phase 1에서는 ADR-0011 이전 과도기 해법이 필요.

추가 발견 [E3]: 데몬 `print()` 출력이 cp949(Windows 한국어 기본) 인코딩으로 stdout에 가서 PowerShell 리다이렉트 파일에 cp949로 저장. UTF-8로 읽으면 mojibake (`���� �⵿`). structlog JSON 로그는 UTF-8 정상.

## Decision

1. **Python `logging.handlers.RotatingFileHandler` 자동 부착**
   - `signal serve --start-daemon` 시 자동 활성화
   - 로그 위치: `logs/daemon.log`, 5MB 로테이션 × 7개 보존(35MB max per session)
   - 형식: structlog JSON 한 줄당 한 이벤트
2. **`PYTHONIOENCODING=utf-8` + `sys.stdout.reconfigure` 강제**
   - 데몬 부팅 시 `sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")` 호출
   - 환경변수 미설정 시 자동 보강
   - cp949 stdout [E3] 해결
3. **`signal serve --log-file <path>` CLI 옵션**
   - 기본값 `logs/daemon.log`, 사용자 커스텀 경로 허용
   - 기존 운영자가 별도 위치에 묶고 싶으면 사용
4. **종료 사유 캡처:** `runner_handle.py`의 `_supervise` 예외 캐치 시:
   - `structlog`로 `daemon_crashed` 이벤트 + exception type/message 기록
   - 마지막 50줄 stdout buffer dump (가능한 경우)

## Consequences

**Positive:**
- silent restart 다음 사고부터 사유 추적 가능 (D+0~D+2 4번째 사고가 ADR-0013 검증 데이터)
- cp949 mojibake [E3] 해결
- ADR-0011 nssm 정식 도입 전까지 관측성 공백 메움
- v2.0.4 핫픽스 트랙 외 코드 변경 없이 v2.1 Phase 1 진입 가능
- 운영자가 `Get-Content logs/daemon.log -Tail 20`만으로 데몬 상태 확인 가능

**Negative:**
- `logs/` 폴더 디스크 누적 (5MB × 7 = 35MB max per session)
- ADR-0011 nssm 도입 시 `AppStdout`/`AppStderr` 옵션과 일부 중복 → 재검토 필요
- D+2 [E] PowerShell 우회 (`Start-Process -Redirect...`)는 본 ADR 적용 후 deprecate

**Trade-offs vs ADR-0011 (nssm):**
- nssm: 프로세스 라이프사이클 (자동 재시작) + stdout 캡처. 설치 복잡. Phase 2+ 트랙
- 본 ADR: stdout 캡처 only. 코드 내부 변경. v2.1 Phase 1에 즉시 포함 가능
- 두 ADR은 layer가 다름 (라이프사이클 vs 관측성). nssm 도입 후에도 RotatingFileHandler 공존 가능 (단, AppStdout 중복 시 한쪽 비활성 권장)

## Action Items

- ⏳ v2.1 Phase 1: `signal_program/runner_handle.py`에 RotatingFileHandler 부착 (M14 product brief 패턴 차용)
- ⏳ v2.1: `sys.stdout.reconfigure` + `PYTHONIOENCODING=utf-8` 강제 (cli.py serve 핸들러)
- ⏳ v2.1: `signal serve --log-file <path>` 옵션
- ⏳ v2.1: `_supervise` 예외 캐치 + `daemon_crashed` structlog 이벤트
- ⏳ ADR-0011 nssm 도입 시: 본 ADR 재검토 — RotatingFileHandler 유지 vs nssm AppStdout으로 대체 결정
- ✅ D+2 ad-hoc 우회 (signal.exe + Start-Process -Redirect) — 통합 핸드오프 §2.3에 보존 (v2.1 본 구현 전 D+3~ 임시)
