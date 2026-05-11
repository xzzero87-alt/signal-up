# ADR-0008: 설정 영속화 — `state/settings.json` 단일 source of truth

**Date**: 2026-05-07
**Status**: accepted
**Deciders**: 사용자(태민)

## Context

GUI(R-P0-11)에서 사용자가 화이트리스트·BB/CCI 임계값·텔레그램 토큰 등을 GUI에서 변경·저장하는 시나리오가 v2.0에 추가되었다. 저장처 후보는 (1) `.env` 단일, (2) `state/settings.json` 단일, (3) `.env`(시크릿) + `state/settings.json`(전략) 이원화 세 가지다. `.env` 자동 갱신은 주석/순서 손실 위험이 크고, 이원화는 토큰 변경 시 결국 `.env` 자동 쓰기 정책이 필요해진다.

## Decision

**`state/settings.json`을 단일 source of truth로 한다.** `.env`는 **첫 부팅 부트스트랩**(`state/settings.json`이 없을 때 한 번만 읽어 시드)에만 사용한다. 이후 모든 GUI/런타임 설정 변경은 `state/settings.json`에 직접 직렬화된다. `state/` 디렉토리는 `.gitignore` 처리.

## Alternatives Considered

### Alternative 1: `.env` 단일, GUI 저장 시 자동 갱신
- **Pros**: 단일 파일, 환경변수 표준 형식
- **Cons**: 자동 쓰기 시 주석/순서/포맷 손실. python-dotenv 등은 보존이 안정적이지 않음
- **Why not**: 자동 쓰기 안정성 부족 → 사용자 편집 의도 훼손 위험

### Alternative 2: `.env`(시크릿) + `state/settings.json`(전략) 이원화
- **Pros**: 시크릿과 전략 파라미터 분리, gitignore 정책이 자연스러움
- **Cons**: GUI에서 텔레그램 토큰 변경 시 결국 `.env` 갱신 정책이 다시 필요해짐 → Alt-1 문제 재발
- **Why not**: 분리해도 결국 `.env` 자동 쓰기로 회귀

### Alternative 3: Pydantic Settings의 secrets directory
- **Pros**: 시크릿을 파일 단위로 분리 보관 (Docker/K8s 친화)
- **Cons**: 디렉토리 구조가 자가설치 사용자에게 과함
- **Why not**: KISS 원칙. 단일 사용자 자가설치 모델에서 오버헤드

## Consequences

### Positive
- GUI 저장이 안전한 JSON 직렬화로 끝남 (주석/포맷 손실 무관)
- `.env`는 사용자 수동 편집 + 첫 부트 시드 용도로만 깔끔히 분리
- 단일 source of truth → 동기화 이슈 zero
- `state/`는 gitignore이므로 실수 커밋 위험 최소

### Negative
- 시크릿(텔레그램 토큰)이 JSON에 평문 저장됨 → 파일 권한 600으로 제한, 운영 PC 보안에 의존
- 첫 부팅과 이후 동작이 다른 모드 (부트스트랩 vs 런타임) → 테스트 시 분기 처리 필요

### Risks
- 사용자가 `state/settings.json`을 실수로 git에 커밋 → `.gitignore` 명시 + `signal doctor`에서 git status 검사 가드 검토
- 파일 손상 시 GUI 동작 불가 → 백업 정책(Q6, 운영 1주차에 결정)
- **재검토 시점**: 사용자가 OS 자격증명 저장소(Windows Credential Locker, macOS Keychain) 통합을 요청하면 v2에서 별도 ADR로 검토

## 구현 메모

- 부팅 시퀀스:
  1. `state/settings.json` 존재 → JSON에서 로드
  2. `state/settings.json` 미존재 → `.env`에서 로드해 메모리에만 보유 (자동 직렬화 X). 사용자가 GUI 저장을 한 번 누르면 그때 `state/settings.json` 생성
  3. 환경변수가 둘 다에서 누락된 필수값(`TELEGRAM_BOT_TOKEN` 등) → `signal doctor`에서 경고
- 파일 권한: 생성 시 `chmod 600` (Windows는 ACL로 사용자 단독 RW)
- 시크릿 필드는 응답 직렬화에서 마스킹 (R-P0-11, ADR-0007 정책)

## 관련 자료

- [PRD.md §5.1.2 R-P0-11](../../PRD.md) — 설정 페이지 사양
- [PRD.md §8 Q8](../../PRD.md) — Open Question 종결
- [DESIGN.md §10](../../DESIGN.md) — 환경변수 / 설정 정책
- [ADR-0007](0007-user-owned-bot-token.md) — 토큰 관리와 연계
