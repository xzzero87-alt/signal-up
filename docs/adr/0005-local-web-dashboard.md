# ADR-0005: 로컬 웹 대시보드(FastAPI) 채택

**Date**: 2026-05-07
**Status**: accepted
**Deciders**: 사용자(태민)

## Context

v1.0은 CLI + 텔레그램 단독으로 1인 사용자만 상정했지만, v2.0에서 "다른 사용자도 사용할 수 있는 형태"로 확장하기로 결정했다. GUI 도입은 진입 장벽을 낮추되, 운영 복잡도와 보안 표면을 늘린다. 데스크탑 패키지(.exe/.app)는 빌드·서명·아이콘 등 부수 작업이 많고, 외부 인터넷 SaaS는 인증·DB·결제까지 별도 프로젝트 규모가 된다.

## Decision

**기존 CLI를 유지하면서 로컬 웹 대시보드(FastAPI)를 병행 추가**한다. 기본 바인드는 `127.0.0.1`로 외부 인터넷 노출 없이 `localhost`에서만 접속 가능. `signal serve` 명령으로 웹 서버 + 백그라운드 시그널 루프를 같은 프로세스에서 `asyncio.TaskGroup`으로 동시 구동.

## Alternatives Considered

### Alternative 1: CLI 단독 유지 (v1.0 그대로)
- **Pros**: 가장 단순, 의존성 최소
- **Cons**: 진입 장벽 높음, 비개발자 친화도 낮음
- **Why not**: v2.0 "다른 사용자가 사용할 수 있게" 목표 미달

### Alternative 2: 데스크탑 앱 (Tauri/PyQt)
- **Pros**: 더블클릭 실행으로 비개발자 친화도↑
- **Cons**: 플랫폼별 빌드·서명·아이콘 필요, Rust(Tauri) 또는 PyInstaller 의존성↑
- **Why not**: v1 일정에 부수 작업 부담 큼. P2(향후 검토)로 미룸

### Alternative 3: 외부 인터넷 SaaS
- **Pros**: 사용자 진입 장벽 가장 낮음
- **Cons**: 회원가입·인증·DB·결제·이용약관·개인정보 처리·중앙 봇 관리 모두 필요
- **Why not**: v1 스코프를 크게 초과. 별도 v3 PRD 영역

## Consequences

### Positive
- 크로스플랫폼: 브라우저만 있으면 동작
- FastAPI + 단순 HTML/JS로 빠른 구현
- `localhost` 바인드로 외부 노출 차단 → 보안 표면 최소
- 기존 CLI는 그대로 유지(헤드리스 운영자 호환)

### Negative
- FastAPI/uvicorn/Jinja2 의존성 추가
- 백엔드와 프런트엔드 결합 테스트 필요
- 비-localhost 바인드 시 비밀번호 강제 가드 로직 필요

### Risks
- LAN 노출(`WEB_BIND=0.0.0.0`) 시 시크릿 노출 위험 → 빈 비번 시 시작 거부 가드(ADR-0007과 연계)
- **재검토 시점**: GUI v1 운영 1개월 후 데스크탑 패키지(Tauri) 도입 ROI 검토

## 관련 자료

- [DESIGN.md §7](../../DESIGN.md) — 아키텍처
- [DESIGN.md §13.3](../../DESIGN.md) — 보안 기본선
- [PRD.md §5.1.2](../../PRD.md) — R-P0-10~15
- [ADR-0006](0006-self-hosted-distribution.md) — 자가설치 배포와 연계
