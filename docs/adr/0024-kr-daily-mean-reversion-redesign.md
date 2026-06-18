# ADR-0024: 국장 일봉 전략 — fractal breakout NO-GO, BB+CCI 평균회귀(v1) 채택

**Date**: 2026-06-17
**Status**: accepted
**Deciders**: xzzero87

## Context

ADR-0023으로 국장 일봉 백테스트 경로를 깔고, ADR-0022 Phase 1 게이트로 `KrFractalStrategy`(일봉, breakout)를 검증했다. 43종 동일가중 집계(2022–2025, 비용 반영, max-hold 10):

- 집계 거래수 1,218 (표본 충분), 집계 샤프 중앙값 **+0.09**(평균 +0.02 ≈ 0)
- 누적 중앙값 **−3.8%** vs B&H +23.6%, 강건성 **1/4 연도**만 양(+)

ADR-0022 보류 분기에 따라 파라미터 1라운드(거래량 임계 ×max-hold 9조합, train 2022–2023 / test 2024–2025 OOS)를 수행했으나 train 9조합 전부 음수 샤프, 최적조합 OOS test도 샤프 +0.04로 미달 → **튜닝으로 회복 불가**. 사용자 결정으로 **국장 전략 재설계**로 전환.

재설계의 첫 수로, 신규 코드 없이 기존 카탈로그 시그널 클래스를 KR 일봉(43종, FULL, 비용 반영, 무튜닝 기본 파라미터)에 probe한 결과:

| 시그널 클래스 | 집계 샤프(중앙값) | 누적 중앙값 vs B&H | 판정 |
|---|---|---|---|
| kr_fractal (breakout) | +0.09 | −3.8% vs +23.6% | 미달 |
| v4 Donchian (trend) | +0.06 | −5.1% vs +23.6% | 미달 |
| **v1 BB+CCI (평균회귀)** | **+0.45** (sh>0 31/43) | **+25.8% vs +23.6%** | **통과** |

v1 연도별(43종): 2022 −4.3%(B&H −17.1%)·2023 +6.6%·2024 +6.6%(B&H −15.1%)·2025 +5.6% → **3/4 양(+), 하락장 강력 방어, 매년 +5~7% 안정**. KR 대형주가 추세보다 **평균회귀** 성격이 강함을 시사.

## Decision

1. **`KrFractalStrategy`(일봉) 엣지 NO-GO 확정.** ADR-0017 선례에 따라 라이브 국장은 현행(120분봉 KrFractal) 유지, 신규 라이브 전환·확장 없음.
2. **국장 일봉 전략을 BB+CCI 평균회귀(`v1` 카탈로그)로 재설계 채택.** 신규 시그널을 from scratch로 만들지 않고 기존 `v1`(ADR-0001) 시그널 클래스를 국장 일봉에 적용한다.
3. v1 라이브 전환은 **KR 전용 OOS 확인 1라운드**(train/test 분리, 필요 시 경량 파라미터 점검 — 선택은 OOS로만) 통과를 조건으로 한다. 통과 시 ADR-0023대로 라이브 일봉 전환 + ADR-0018 supersede.
4. ADR-0023 데이터·도구(43종 일봉, `kr_strategy_matrix`, `kr_gate_eval`)를 재사용한다.

## Alternatives Considered

### Alternative 1: 추세추종(v4)/breakout(fractal) 계속
- **Why not**: 43종 probe에서 둘 다 집계 샤프 ≈0·누적 음수. KR 대형주에 엣지 없음.

### Alternative 2: 신규 시그널 from scratch 설계
- **Why not**: 기존 v1 평균회귀가 이미 게이트를 통과. 검증된 단순안을 두고 새로 만드는 것은 과함(simplest-first).

### Alternative 3: 게이트 기준 완화
- **Why not**: 불필요 — v1은 현 기준(샤프>0 & B&H 초과 & 강건성)을 그대로 통과.

## Consequences

### Positive
- 재사용 파이프라인으로 "엣지 없는 fractal → 엣지 있는 평균회귀"를 신규 코드 0으로 전환.
- v1은 **하락장 방어 + 매년 +5~7% 안정 수익** 프로필 — 알림 제품에 적합한 저변동 수익 스트림.
- ADR-0001(BB+CCI)·기존 v1 코드·테스트 자산 재활용.

### Negative
- v1은 **강세장(2025) 열위**(B&H 초과 5/43) — 절대수익으로 강세장 B&H를 못 이김. "알파"보다 "안정·방어" 성격.
- 라이브 전환까지 OOS 확인 1라운드가 추가로 필요.

### Risks
- **In-sample 성격** → 다만 KR 무튜닝(coin 기본 파라미터)이라 과적합 위험 낮음. OOS 확인으로 종결.
- **평균회귀의 약점(추세장 손실)** → 레짐 필터(예: 200일선 상회 시 비중 축소) 추가는 후속 선택지.

## 관련 자료

- [ADR-0022](0022-post-v24-roadmap-edge-first.md) — Phase 1 게이트(통과 기준)
- [ADR-0023](0023-kr-backtest-daily-timeframe.md) — 국장 일봉 백테스트 경로
- [ADR-0017](0017-v2-strategy-no-go-redesign.md) — NO-GO 선례
- [ADR-0018](0018-kr-fractal-strategy.md) — KrFractal(현행 라이브, 전환 시 supersede 대상)
- [ADR-0001](0001-bb-cci-indicators.md) — BB+CCI 지표 조합
- `reports/compare/kr_strategy_matrix.csv` — kr_fractal 43종 게이트 데이터
