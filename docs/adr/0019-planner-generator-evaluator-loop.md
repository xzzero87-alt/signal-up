# ADR-0019: 개발 진행 구조 — Planner / Generator / Evaluator 루프

**Date**: 2026-06-08
**Status**: accepted
**Deciders**: xzzero87

## Context

전략·UI 확장이 잦아지면서 "계획 없이 구현 → 게이트에서 뒤늦게 실패" 패턴이 반복됐다. 실제로 전략 v2.3 작업에서 settings.html이 게이트 누락 상태로 진행돼 회귀가 발생했다. 품질 게이트 4종(ruff·mypy·pytest·ui_check)과 UI 역할 분담(`ui/agent-roles.md`)은 이미 있으나, 이를 묶는 상위 진행 구조가 문서화돼 있지 않았다.

## Decision

모든 비자명 작업을 **Planner → Generator → Evaluator** 3단계 루프로 진행한다. Planner와 Evaluator는 읽기 전용, Generator만 쓰기 권한을 가진다. Evaluator의 합격 루브릭은 기존 품질 게이트 4종이며, 미달 시 Generator로 반송한다. 운영 세부는 [`../dev-loop.md`](../dev-loop.md), UI 하위 역할은 [`../ui/agent-roles.md`](../ui/agent-roles.md)를 따른다.

## Alternatives Considered

### Alternative 1: 단일 에이전트 자유 진행 (현행 유지)
- **Pros**: 오버헤드 없음, 작은 작업에 빠름.
- **Cons**: 계획·평가 단계가 암묵적이라 게이트 누락·범위 이탈이 늦게 드러남.
- **Why not**: v2.3 회귀처럼 실패 비용이 콜드스타트 반복보다 커지는 사례가 누적됨.

### Alternative 2: 전 작업 강제 다중 에이전트 오케스트레이션
- **Pros**: 역할 격리 명확, 병렬화 가능.
- **Cons**: 에이전트 콜드스타트 비용이 작업마다 누적, 사소한 수정에 과함.
- **Why not**: 비용 대비 실익이 작은 작업이 많음. 루프는 채택하되 다중 에이전트는 작업 규모에 따라 선택 적용.

## Consequences

### Positive
- 계획·평가가 명시 단계가 되어 게이트 누락·범위 이탈을 조기 차단.
- 합격 기준이 기존 게이트 4종으로 고정 — 별도 루브릭 불필요.
- `/gan-build`·`/gan-design`·`/santa-loop` 등 기존 루프 도구에 바로 매핑.

### Negative
- 작은 수정에도 단계 의식이 필요 — 자명한 작업은 판단으로 생략 허용(CLAUDE.md 트레이드오프 조항).

### Risks
- 루프 반복·다중 에이전트로 비용 급증 → 라운드 수 상한·작업 규모별 적용으로 완화.

## 관련 자료

- [dev-loop.md](../dev-loop.md) — 운영 가이드
- [ui/agent-roles.md](../ui/agent-roles.md) — UI 하위 역할
- [ADR-0002](0002-no-autotrading.md) — Generator 하드라인(자동매매 금지)
- [.claude/CLAUDE.md](../../.claude/CLAUDE.md) §변경 금지 영역·핵심 명령
