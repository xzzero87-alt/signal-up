# ADR-0011: Windows Service 등록 방식 — nssm 채택

**Date**: 2026-05-20
**Status**: accepted
**Deciders**: 태민 (프로젝트 오너)

## Context

v2.0 운영 중 D+0 사고에서 PowerShell 창을 닫으면 데몬이 함께 종료되는 근본 문제가 확인됐다. 이를 해결하기 위해 v2.1-e(Windows Service) 기능을 설계하고 있으며, Windows 서비스로 등록하면 로그인 없이도 자동 시작·OS 레벨 재기동이 보장된다. Python `uv run signal serve` 프로세스를 Windows 서비스로 래핑하는 방법을 결정해야 한다. 선택지는 **nssm**, **sc.exe + 래퍼 스크립트**, **WinSW** 세 가지다.

## Decision

`nssm`(Non-Sucking Service Manager)을 사용하여 Windows 서비스를 등록한다. `install_service.ps1` / `uninstall_service.ps1` 스크립트를 프로젝트 루트에 배포하고, `signal doctor` 명령에 서비스 상태 체크를 추가한다.

## Alternatives Considered

### Alternative 1: sc.exe + 래퍼 배치 스크립트

Windows 기본 내장 도구로 외부 의존성이 전혀 없다.

- **Pros**:
  - 추가 설치 불필요 — 모든 Windows 버전에 포함
  - 신뢰할 수 있는 Microsoft 공식 도구
  - PowerShell `sc.exe` 스크립트만으로 설치/제거 자동화 가능

- **Cons**:
  - Python 프로세스의 stdout/stderr을 서비스 로그로 자동 캡처하지 않음
  - 서비스가 직접 실행할 `.exe`가 필요하므로 `uv run` 가상환경 경로 처리가 복잡
  - 환경변수(`.env`) 전달을 위한 별도 래퍼 스크립트 필수
  - 서비스 재시작 정책(지수 백오프 등)을 GUI 또는 레지스트리로만 설정 가능

- **Why not**: stdout 캡처 부재가 치명적. 데몬 오류를 서비스 이벤트 로그에서만 확인해야 하며, 기존 structlog 로그 파일과 통합하기 어렵다. Python venv 경로 래핑도 오류 가능성을 높인다.

---

### Alternative 2: WinSW (Windows Service Wrapper)

Jenkins 생태계에서 자주 쓰이는 XML 기반 서비스 래퍼. GitHub에서 활발히 유지보수 중.

- **Pros**:
  - XML 설정 파일로 환경변수·재시작 정책·로그 롤링을 선언적으로 관리
  - stdout/stderr 자동 캡처 및 일별 로그 롤링 지원
  - `.exe` 단일 파일 배포 (레지스트리 불필요)

- **Cons**:
  - `.exe` 파일을 미리 다운로드해야 하며, `.NET` 런타임 버전에 따라 호환성 문제 발생 가능
  - `winSW.exe`와 `winSW.xml` 두 파일을 프로젝트에 포함하거나 설치 스크립트로 다운로드해야 함
  - nssm 대비 한국어 자료가 부족하고, 커뮤니티 레퍼런스가 적음
  - 초기 설정이 XML이라 PowerShell 스크립트 자동화와 궁합이 약간 어색

- **Why not**: nssm에 비해 사용자가 직접 디버깅하기 어렵고, `.NET` 버전 의존성이 추가 변수를 만든다. 기능 면에서는 동등하지만 학습 비용과 레퍼런스 접근성이 낮다.

---

### Alternative 3: nssm (Non-Sucking Service Manager) ← **채택**

오픈소스 Windows 서비스 매니저. 사전 설치 또는 프로젝트 내 동봉 가능.

- **Pros**:
  - Python 프로세스를 직접 서비스로 래핑 — `uv.exe`를 Application으로 지정하고 `run signal serve`를 Arguments로 전달하는 단순한 구조
  - stdout/stderr 파일 자동 캡처 (`AppStdout`, `AppStderr` 설정 한 줄)
  - 재시작 정책(즉시/지수 백오프/n회 후 포기)을 nssm GUI 또는 `nssm set` CLI로 관리
  - `.env` 파일 경로를 Environment 탭 또는 `nssm set <svc> AppEnvironmentExtra` 로 전달 가능
  - 단일 `.exe` 파일 — `tools/nssm.exe`로 프로젝트에 동봉하거나 Chocolatey/Scoop 설치 모두 가능
  - 한국어 블로그·문서가 풍부하고 Windows Python 서비스화 레퍼런스 다수

- **Cons**:
  - 외부 도구 의존성 — 사용자가 `nssm.exe`를 설치하거나 프로젝트 내 동봉해야 함
  - 마지막 공식 릴리스(2.24)가 2014년이나, 2017년 pre-release(2.24-101) 이후 별다른 버그 미보고 — 실질적으로 안정적
  - antivirus에서 nssm.exe를 오탐하는 사례가 드물게 있음 (대형 AV 제품군 기준 false positive 거의 없음)

- **Why chosen**: stdout 자동 캡처, 단순한 Python/uv 연동, 직관적인 CLI 자동화(`nssm install`, `nssm set`, `nssm remove`)의 조합이 가장 낮은 구현 복잡도와 높은 운영 편의성을 동시에 제공한다.

## Consequences

### Positive

- PowerShell 창 종속성 완전 제거 — OS 부팅 시 자동 시작, 로그인 불필요
- 데몬 stdout/stderr가 `logs/service_stdout.log` / `logs/service_stderr.log`에 자동 저장 → 장애 추적 가능
- `nssm set SignalUp AppRestartDelay 5000` 한 줄로 서비스 재기동 정책 설정
- `install_service.ps1` / `uninstall_service.ps1` 스크립트로 사용자 설치 자동화
- `signal doctor`에 서비스 상태 체크 통합 → 환경 점검 원스톱

### Negative

- 사용자가 `nssm.exe`를 별도 설치하거나, 프로젝트 배포 시 `tools/nssm.exe` 동봉 필요
- nssm 서비스로 실행 시 작업 디렉토리(CWD)와 환경변수를 스크립트에서 명시적으로 지정해야 함 — 설치 스크립트에 `AppDirectory` 설정 포함 필수

### Risks

- **AV 오탐**: nssm.exe 실행 시 일부 AV 소프트웨어가 차단할 수 있음.
  → 완화: README에 VirusTotal 링크 및 SHA-256 체크섬 제공, Chocolatey/Scoop 설치 경로를 1순위 권장으로 안내.
- **경로 공백 문제**: `C:\Program Files\...` 처럼 공백이 포함된 경로에서 `nssm set` 인자가 잘못 파싱될 수 있음.
  → 완화: `install_service.ps1`에서 경로를 큰따옴표로 감싸고, `AppDirectory`를 절대 경로로 명시.
- **`.env` 비밀 노출**: nssm 환경 설정이 레지스트리에 평문으로 저장됨.
  → 완화: 레지스트리는 로컬 관리자 권한 필요 — 단일 사용자 로컬 운영 환경에서 위험 수준 낮음. 공유 PC 사용 시 README에 경고 명시.

## 구현 메모 (Sprint 3 참조용)

```powershell
# install_service.ps1 핵심 흐름 (의사코드)
$nssm = ".\tools\nssm.exe"       # 또는 where.exe nssm
$svcName = "SignalUp"
$uvPath = (Get-Command uv).Source  # C:\Users\...\uv.exe
$appDir  = $PSScriptRoot

& $nssm install $svcName $uvPath
& $nssm set $svcName AppParameters "run signal serve"
& $nssm set $svcName AppDirectory $appDir
& $nssm set $svcName AppEnvironmentExtra "SIGNAL_ENV_FILE=$appDir\.env"
& $nssm set $svcName AppStdout "$appDir\logs\service_stdout.log"
& $nssm set $svcName AppStderr "$appDir\logs\service_stderr.log"
& $nssm set $svcName AppRotateFiles 1
& $nssm set $svcName AppRestartDelay 5000
& $nssm set $svcName Start SERVICE_AUTO_START
Start-Service $svcName
```

- `signal doctor` 체크 항목: `sc query SignalUp` 실행 → STATE 파싱 → `RUNNING` / `STOPPED` / `NOT_INSTALLED` 세 상태 출력
- 수동 업데이트 절차: `Stop-Service SignalUp` → `git pull` → `uv sync` → `Start-Service SignalUp`

## 관련 자료

- [PRD.md §4 — v2.1 기능 목록](../PRD.md)
- [DESIGN.md §10 — 환경변수 설정](../DESIGN.md)
- [ADR-0002](0002-no-autotrading.md) — 자동매매 제외 (서비스 범위 한정)
- [v2.1 구현 계획](../../plans/v2.1-implementation-plan.md) — Step-E (Sprint 3) 상세
- [nssm 공식 사이트](https://nssm.cc/)
- [nssm GitHub pre-release 2.24-101](https://github.com/kirsteins/nssm)
