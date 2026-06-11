# ADR-0021: 백테스트 청산 로직의 전략 위임 (SupportsExit 선택 프로토콜)

**Date**: 2026-06-11
**Status**: accepted
**Deciders**: 태민, Cowork 설계 세션

## Context

백테스트 엔진의 청산 규칙(`max_holding_bars` 또는 `close >= bb_middle`)은 v1 BB+CCI 전용 설계다.
전략 비교 매트릭스(plans/strategy-comparison-matrix.md) 과정에서 비-BB 전략(v3/v4/v5)이
`bb_middle=0.0`으로 1봉 청산되는 버그가 발견돼 `bb_middle > 0` 가드로 임시 수정했으나(81807e0),
그 결과 v3/v4/v5는 일률적 24봉 시간 청산으로만 평가된다. 특히 v4 Donchian은 고유 청산 파라미터
(`donchian_exit_period` 채널)를 갖고 있음에도 엔진이 사용하지 못한다. 매트릭스에서 v4가 진입 신호
품질 기준 최상위(B&H 대비 9/15칸, +13.4pp)로 나타나 고유 청산 포함 재평가가 필요하다.
변하지 않는 전제: DESIGN.md §8.1~8.5 기존 시그니처 수정 금지 (신규 추가는 허용).

## Decision

`strategies/base.py`에 **선택적 보조 프로토콜** `SupportsExit`를 신규 추가한다:

```python
@runtime_checkable
class SupportsExit(Protocol):
    def should_exit(self, market: str, candles: pd.DataFrame, entry_bar_idx: int) -> bool: ...
```

엔진은 보유 중 매 봉에서 `isinstance(strategy, SupportsExit)`이면 청산 판단을 전략에 위임하고,
이때 BB 중심선 타깃 청산은 적용하지 않는다. `max_holding_bars`는 **안전 캡으로 항상 유지**한다.
`candles`는 기존 evaluate 컨벤션과 동일하게 시작~현재 봉(마감) 포함 슬라이스, 평가는 봉 마감 기준.
구현은 v4 Donchian(직전 `donchian_exit_period`봉 최저 low 하향 마감 시 청산)부터 하고,
v3/v5는 필요해질 때 추가한다 (YAGNI).

## Alternatives Considered

### Alternative 1: Strategy Protocol에 should_exit 필수 메서드 추가
- **Pros**: 모든 전략이 청산을 명시, 엔진 분기 없음
- **Cons**: 5개 전략 + 테스트 mock 전부 수정, 기존 Protocol 계약 변경에 해당할 소지
- **Why not**: §8 hard line 회색지대를 건드리고 변경 반경이 큼. 선택 프로토콜이면 기존 코드 무수정

### Alternative 2: Signal에 정적 exit_target 필드 추가
- **Pros**: 모델 필드 추가만으로 해결 (명시적 허용 범위)
- **Cons**: Donchian 청산은 진입 시점에 못 정하는 **동적 채널**(매 봉 갱신) — 정적 타깃으로 표현 불가
- **Why not**: 핵심 사용처인 v4를 표현하지 못함

### Alternative 3: 엔진에서 전략 이름 문자열 분기
- **Pros**: 가장 적은 코드
- **Cons**: 엔진이 전략 내부 지식에 결합, 전략 추가 시마다 엔진 수정 (OCP 위반)
- **Why not**: 전략 카탈로그(ADR-0010)의 확장 방향과 충돌

## Consequences

### Positive
- v4를 설계대로 평가 가능, 이후 전략도 청산 로직을 자기 파일 안에 캡슐화
- 기존 v1 경로·시그니처·테스트 무수정 (isinstance 분기 1곳)

### Negative
- 청산 규칙이 엔진/전략 두 곳에 분산 — "위임 시 타깃 미적용, 캡 유지" 규칙을 docstring에 명문화 필요

### Risks
- 보유 매 봉 should_exit 호출로 백테스트 속도 저하 → Donchian은 rolling min 단순 연산, 실측상 무시 가능
- max_holding_bars(24) 캡이 채널 청산보다 먼저 발동해 v4 성격 왜곡 가능 → 재실행 후 avg_bars_held
  분포 확인, 24에 몰리면 캡 상향을 별도 논의

## 관련 자료

- plans/strategy-comparison-matrix.md §8 (시그널 프로그램 폴더) — 매트릭스 결과·버그 진단
- docs/prompts/backtest-engine-exit-guard-prompt.md — 선행 버그 수정 (81807e0)
- docs/prompts/strategy-owned-exit-prompt.md — 본 ADR 구현 핸드오프
- ADR-0010 (전략 카탈로그), DESIGN.md §6 (시뮬레이션 규칙)
