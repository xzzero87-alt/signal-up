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
| [0009](0009-windows-atomic-write.md) | Windows에서 atomic write 우회 (플랫폼 분기) | accepted | 2026-05-12 |
| [0010](0010-strategy-catalog.md) | Strategy 카탈로그 + OBV 거래량 지표 + 가중치 조합 로직 (V2) | accepted | 2026-05-21 |
| [0011](0011-windows-service.md) | Windows Service 등록 방식 — nssm 채택 | accepted | 2026-05-20 |
| [0012](0012-signals-jsonl-canonical.md) | `signals.jsonl` 영속 파일 정식화 + `STATE_SIGNALS_FILE` 상수 | accepted | 2026-05-21 |
| [0013](0013-daemon-stdout-redirect.md) | 데몬 stdout/stderr 파일 리다이렉트 + 일별 로테이션 | accepted | 2026-05-21 |
| [0014](0014-operation-guide-path-sync.md) | 운영 가이드 ↔ 코드 path/key 강제 동기화 정책 | accepted | 2026-05-21 |
| [0015](0015-korean-stock-market-support.md) | 국내 주식(KOSPI/KOSDAQ) 시장 지원 추가 | accepted | 2026-05-21 |
| [0016](0016-kis-api-korean-stock-datasource.md) | KIS Open API (한국투자증권) 국내 주식 데이터 소스 채택 | accepted | 2026-05-21 |
| [0017](0017-v2-strategy-no-go-redesign.md) | V2 전략 D+7 NO-GO 판정 — v1 운용 유지 + V2 재설계 | accepted | 2026-05-27 |
| [0018](0018-kr-fractal-strategy.md) | 국내 주식 시그널 전략 — Williams Fractal 기반 (`KrFractalStrategy`) | accepted | 2026-05-28 |

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
