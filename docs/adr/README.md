# Architecture Decision Records

이 디렉토리에는 **업비트 시그널 프로그램**의 핵심 아키텍처 결정이 ADR(Architecture Decision Record) 형식으로 기록되어 있다. 각 ADR은 [Michael Nygard 형식](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)을 따르며, `everything-claude-code:architecture-decision-records` 스킬 가이드에 맞춰 작성되었다.

## 인덱스

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-bb-cci-indicators.md) | BB + CCI 지표 조합 채택 | accepted | 2026-05-07 |
| [0002](0002-no-autotrading.md) | 자동매매 제외 | accepted | 2026-05-07 |
| [0003](0003-telegram-only-channel.md) | 텔레그램 단일 알림 채널 | accepted | 2026-05-07 |
| [0004](0004-single-1h-timeframe.md) | 1시간봉 단일 타임프레임 | accepted | 2026-05-07 |
| [0005](0005-local-web-dashboard.md) | 로컬 웹 대시보드(FastAPI) 채택 | accepted | 2026-05-07 |
| [0006](0006-self-hosted-distribution.md) | 오픈소스 자가설치 배포 | accepted | 2026-05-07 |
| [0007](0007-user-owned-bot-token.md) | 사용자 자가 텔레그램 봇 토큰 | accepted | 2026-05-07 |
| [0008](0008-settings-storage.md) | 설정 영속화 — `state/settings.json` 단일 source of truth | accepted | 2026-05-07 |

## 작성 규칙

- 새 ADR은 다음 일련번호로 추가 (`0008-...`).
- 파일명: `NNNN-kebab-case-title.md` (4자리 zero-pad).
- 기본 템플릿은 [`template.md`](template.md) 복사 후 작성.
- 결정이 바뀌면 기존 ADR을 **삭제하지 않고** Status를 `superseded by ADR-NNNN`으로 변경하고, 새 ADR에서 이전 ADR을 명시 참조.
- 각 ADR은 **2분 이내 읽기 가능한 길이** 유지. Context 섹션은 10줄 이내.
- Status: `proposed` → `accepted` → `deprecated` 또는 `superseded`.

## 연관 문서

- [`../../PRD.md`](../../PRD.md) — Product Requirements Document (v2.0)
- [`../../DESIGN.md`](../../DESIGN.md) — 기술 명세서 (v2.0)
- [`../../.claude/CLAUDE.md`](../../.claude/CLAUDE.md) — 프로젝트 가이드
