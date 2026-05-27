# ADR-0017: V2 전략 D+7 NO-GO 판정 — v1 운용 유지 + V2 재설계

**Date**: 2026-05-27
**Status**: accepted
**Deciders**: 프로젝트 오너

## Context

ADR-0010에서 설계한 V2 전략(FourIndicatorStrategy: BB·CCI·Stochastic·OBV 가중치 조합)을
구현 완료하고 D+7 워크포워드 백테스트로 검증하였다.
그리드 서치(9셀 파라미터 공간) + 워크포워드 폴드 결과, V2는 D+7 기준
**GO 판정을 충족하지 못했다** (기준 지표: 샤프 비율·승률·드로다운 비율 중 다수 미달).
V1(BbCciStrategy)은 현재 운용 중이며 기준 성능을 유지하고 있다.

## Decision

V2 전략 현행 구현(`FourIndicatorStrategy`)은 운용 투입을 보류하고,
기존 **V1(BbCciStrategy) 운용을 유지**한다.
V2는 지표 조합·가중치·임계값 전면 재검토 후 재설계한다.

## Alternatives Considered

### Alternative 1: V2 결과를 감수하고 즉시 운용 투입
- **Pros**: 신규 지표(STO·OBV) 실전 피드백 즉시 수집 가능
- **Cons**: 백테스트 NO-GO 전략을 실전에 노출 → 의도치 않은 손실 위험
- **Why not**: 프로젝트 원칙("참고용 시그널, 자동매매 없음")에서도 신뢰도 낮은 시그널 송출은 금지

### Alternative 2: V2 코드 전체 삭제 후 V1 단일 유지
- **Pros**: 코드베이스 단순화
- **Cons**: 재설계 시 처음부터 재작성 필요; 그리드 서치·워크포워드 인프라가 낭비됨
- **Why not**: 기존 구현체(FourIndicatorStrategy, grid_search, walkforward V2 지원)는
  재설계 기반으로 재활용 가능하므로 유지

## Consequences

### Positive
- V1 시그널 품질·연속성 유지
- V2 재설계 시 기존 백테스트 파이프라인(그리드 서치·워크포워드·D+7 GO/NO-GO 표) 재사용
- `strategy_version` 파라미터로 V1/V2 전환이 이미 CLI에서 가능 → 재설계 후 전환 비용 최소

### Negative
- V2 코드(`FourIndicatorStrategy`, `v2_4indicator.py`)가 당분간 미사용 상태로 잔류
- 재설계 일정 미확정 → 기술 부채 누적 가능

### Risks
- **재설계 지연**: V2 목표 지표·설계 기준을 PRD Phase 2에 명시하여 범위 관리
- **V1 과의존**: V1 성능이 시장 변화로 저하될 경우 대안 없음
  → 완화: 월 단위 V1 워크포워드 재검증 권장

## 관련 자료

- [ADR-0010](0010-strategy-catalog.md) — Strategy 카탈로그 + V2 설계 원안 (운용 보류)
- [PRD.md](../../PRD.md) — Phase 2 재설계 범위 정의 예정
- [DESIGN.md §11](../../DESIGN.md) — 백테스트 파이프라인 명세
