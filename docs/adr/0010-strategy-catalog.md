# ADR-0010: Strategy 카탈로그 + OBV 거래량 지표 + 가중치 조합 로직 (V2)

**Status:** Accepted (2026-05-21, D+2 게이트 즉시 종료로 D+7 → D+2 앞당김)
**Date:** 2026-05-19
**Deciders:** xzzero87-alt (사용자, crypto_trader_only 페르소나)
**Supersedes:** —
**Related:**
- ADR-0001 (BB+CCI 채택, V1 정의)
- ADR-0002 (자동매매 X, 영구)
- ADR-0004 (1H 단일 타임프레임)
- ADR-0008 (settings.json single source of truth)
- `..\..\PRD_v2.1_phase1_strategy_v2.md` (Phase 1 PRD)
- 메모리 `feedback_signal_program_framing` (v2.1/v3.0 reinforce 보강)

## Context

v2.0.3까지 BB(20-2) + CCI(20) 단일 전략(V1)을 1H봉으로 운영. 사용자가 본인 매매 결정 도구로 사용하면서 다음 매매 스타일이 명확해짐 (2026-05-19 ADR-0010 elicitation):

- **거짓 시그널 최소화** — 강한 확신만 발사
- **거래량을 가장 중요시** — 다른 지표 대비 가중치 높음
- **추세 추종형** — 모멘텀 확인 핵심
- **분할 매수 선호** — 적당한 시그널 빈도 필요

이 스타일에 맞춰 4지표(BB + CCI + 스토캐스틱 슬로우 + 거래량) 통합 시그널(V2)을 추가. PRD §2 G1.

**ADR이 답해야 할 4가지:**
1. **OQ1** 거래량 지표: OBV 신규 vs `volume_ratio_min_a/b` 확장
2. **OQ2** 4지표 조합 로직: AND 엄격 vs AND 느슨 vs 가중치 vs 비대칭
3. **OQ3** 스토 임계값 기본값: 20/80 vs 25/75 vs 15/85
4. Strategy 카탈로그 패턴: V1/V2 등록·조회·확장 (기술 결정)

**변경 금지 (Hard Lines):**
- DESIGN.md §8.4 `Strategy` Protocol 시그니처 (불변)
- 자동매매 X (ADR-0002)
- 1H 타임프레임 (ADR-0004, Phase 3까지)
- ADR-0008 settings.json single source

## Decision

### 1. 거래량 지표 — OBV 신규 도입

신규 함수 `compute_obv(candles) -> OBVSnapshot`. V2 고유 지표로 V1과 명확히 구분.

**Why:**
- 사용자가 "거래량을 가장 중요시" 명시 → OBV가 V2 score에서 가중치 0.40 (다른 지표 2배)
- 기존 `volume_ratio_min_a/b`는 V1 squeeze 검출용 — 역할이 다름. V1에서 그대로 유지
- V1과 V2의 차이가 "지표 2개 더"가 아니라 "다른 거래량 신호 + 가중치 모델"로 명확

**기존 인프라 재사용 X 결정 근거:**
- V1과 V2 구분 명확성 ↑
- 사용자가 V2의 거래량 시그널을 OBV로 직접 해석 가능 (누적 거래량 + 가격 방향 일치)
- volume_ratio는 V1 코드에 깊이 박혀 있어 확장 시 V1 회귀 위험

### 2. 조합 로직 — 가중치 점수제

각 지표가 0~1 score 산출 → 가중 합산 → 임계값 이상이면 발사.

```python
score_total = (
    bb_weight   * score_BB
  + cci_weight  * score_CCI
  + sto_weight  * score_Sto
  + obv_weight  * score_OBV
)
# 매수 발사: score_total >= buy_threshold (기본 0.65)
# 매도 발사: 대칭으로 매도 score_total >= sell_threshold (기본 0.65)
```

**기본 가중치 (사용자 거래량 중시 반영):**

| 지표 | 가중치 | 사유 |
|---|---|---|
| OBV | **0.40** | 사용자가 "거래량 가장 중요시" 명시 |
| BB | 0.20 | 진입 신호 (평균회귀 보조) |
| CCI | 0.20 | 모멘텀 확인 (추세 추종 핵심) |
| Sto | 0.20 | 과매수/과매도 보조 확인 |
|  | = 1.00 |  |

**기본 임계값:** `buy_threshold = sell_threshold = 0.65`. 사용자 GUI 튜닝 가능.

**Why 가중치 점수제 (vs AND/비대칭):**

| 옵션 | 적합도 | 이유 |
|---|---|---|
| AND 3 (느슨) | ⚠️ 부분 | 모든 지표 동등 — "거래량 가장 중요시" 표현 불가 |
| AND 4 (엄격) | ⚠️ 부분 | 시그널 너무 적음, 분할 매수에 불충분 |
| 비대칭 매수/매도 | ❌ 부적합 | 추세 추종에 매수/매도 대칭이 자연 |
| **가중치 점수제** | ✅ 채택 | "거래량 중시 + 거짓 시그널 최소화 + 사용자 튜닝" 모두 충족 |

**Score 함수 — 각 지표별 0~1 매핑 (매수 기준):**

| 지표 | 매수 score 공식 (0~1) |
|---|---|
| BB | `max(0, 1 - (close - bb_lower) / (bb_middle - bb_lower))` — 하단 터치하면 1, 중앙선이면 0 |
| CCI | `max(0, min(1, -CCI / 200))` — CCI ≤ -200이면 1.0, 0이면 0, +값은 0 |
| Sto | `max(0, 1 - %K / 15)` — %K ≤ 0이면 1.0, ≥ 15이면 0 (Sto 15/85 임계값 OQ3 반영) |
| OBV | OBV 직전 N=20봉 평균 대비 증가율을 0~1 clip. `min(1, max(0, (obv_now - obv_avg) / obv_avg))` |

매도는 대칭 (BB 상단 = 1, CCI ≥ +200 = 1, Sto ≥ 85 = 1, OBV 하락).

### 3. 스토캐스틱 슬로우 임계값 — 15 / 85 (엄격)

- 과매도 < 15, 과매수 > 85
- 기본값 `sto_oversold = 15`, `sto_overbought = 85`
- 사용자 GUI에서 조정 가능

**Why 15/85 (vs 20/80 관용, vs 25/75 보수):**
- 사용자 "거짓 시그널 최소화" 스타일과 정합
- 가중치 점수제와 결합 시 Sto가 1.0 score 받는 영역이 작아 score_total 0.65 달성 어려움 → 자연스럽게 strict
- 시그널 빈도 ↓이지만 분할 매수에는 충분 (1H봉이라 일 1~3건이면 적정)

### 4. Strategy 카탈로그 패턴 — Module-level Registry

```python
# src/signal_program/strategies/__init__.py
from typing import Protocol
from .v1_bb_cci import BBCCIStrategy
from .v2_4indicator import FourIndicatorStrategy
from ..config import Settings

STRATEGY_CATALOG: dict[str, type[Strategy]] = {
    "v1": BBCCIStrategy,
    "v2": FourIndicatorStrategy,
}

def get_strategy(version: str, settings: Settings) -> Strategy:
    if version not in STRATEGY_CATALOG:
        raise ValueError(
            f"전략 버전은 {list(STRATEGY_CATALOG.keys())} 중 하나여야 합니다 (입력: {version})"
        )
    return STRATEGY_CATALOG[version](settings)
```

**Why Module registry (vs Enum, vs config-driven):**

| 패턴 | 평가 | 채택 여부 |
|---|---|---|
| Enum (예: `StrategyVersion.V1`) | 타입 안전 ↑, Phase 2 빌더에서 동적 등록 ↓ | ❌ |
| Config-driven (yaml/json에 strategy 정의) | 너무 동적, 매매 도구의 신뢰성 ↓, 검증 어려움 | ❌ |
| **Module registry (dict)** | 명시적 등록 + Python 타입 힌트 + Phase 2 확장 자연 | ✅ |

Phase 2 (전략 빌더)에서 사용자 정의 전략을 카탈로그에 동적 등록 가능. 단 Phase 1에서는 v1/v2 정적 등록만.

DESIGN.md §8.4 `Strategy` Protocol은 그대로 유지. 카탈로그는 §8.4 보강(신규 부록)으로 명시 — 시그니처 불변.

## Options Considered

### Option A: OBV 신규 + AND 3개 (느슨)

| Dimension | Assessment |
|---|---|
| 복잡도 | Low |
| 사용자 매매 스타일 정합 | Medium (거래량 중시 표현 불가) |
| 거짓 시그널 최소화 | Medium |
| 사용자 튜닝 가능성 | Low |
| Phase 2 빌더 확장성 | Low |

**Pros:** 구현 단순, 검증 쉬움.
**Cons:** "거래량 가장 중요시" 사용자 의도 표현 못 함. 가중치 개념 없으면 Phase 2 빌더가 빈약.

### Option B: OBV 신규 + 가중치 점수제 (채택)

| Dimension | Assessment |
|---|---|
| 복잡도 | Medium |
| 사용자 매매 스타일 정합 | **High** |
| 거짓 시그널 최소화 | **High** (임계값 조정으로) |
| 사용자 튜닝 가능성 | **High** (GUI 가중치/임계값) |
| Phase 2 빌더 확장성 | **High** (빌더 = 가중치 정의 UI) |

**Pros:** 사용자 의도 정확 반영. Phase 2 빌딩 블록.
**Cons:** 구현 + 테스트 복잡 ↑. Score 함수 정규화 신중 필요.

### Option C: volume_ratio 확장 + AND 4개 (엄격)

| Dimension | Assessment |
|---|---|
| 복잡도 | Low |
| 사용자 매매 스타일 정합 | Low (V1과 V2 구분 모호) |
| 거짓 시그널 최소화 | High |
| 사용자 튜닝 가능성 | Low |
| Phase 2 빌더 확장성 | Low |

**Pros:** 인프라 재사용, 가장 단순.
**Cons:** V1/V2 차이가 "지표 2개 더" 정도. 도입 가치 ↓.

## Trade-off Analysis

| 결정 축 | 선택 | 포기 |
|---|---|---|
| 거래량 지표 | OBV 신규 (V1/V2 명확 구분) | 인프라 재사용성 |
| 조합 로직 | 가중치 점수제 (사용자 매매 스타일 정합) | 구현 단순성, 검증 부담 |
| Sto 임계값 | 15/85 엄격 (거짓 시그널 ↓) | 시그널 빈도 |
| 카탈로그 패턴 | Module registry | Enum 타입 안전성, config 동적성 |

**가중치 점수제 채택의 핵심 근거:**

사용자 매매 스타일 4요소가 모두 가중치 점수제에 정합:
1. **"거래량 가장 중요시"** → OBV 가중치 0.40 (다른 지표 2배). AND는 표현 불가.
2. **"거짓 시그널 최소화"** → 임계값을 0.70~0.80으로 조정 가능. 사용자 튜닝.
3. **"추세 추종"** → CCI 가중치 0.20 유지 + OBV 추세 일치 검출.
4. **"분할 매수 선호"** → 시그널 빈도가 적당히 있어야 함. AND 4는 너무 적음, AND 3은 가중치 표현 불가. 가중치 + 0.65 임계값이 균형.

## Consequences

### 쉬워지는 것
- 사용자가 본인 매매 스타일을 **가중치 + 임계값**으로 직접 정의 가능
- V1/V2가 명확히 다른 시그널 (OBV로 구분)
- 백테스트/워크포워드에 가중치 그리드 서치 가능 (사용자 선택)
- **Phase 2 (빌더) 도입 시 가중치 시스템 그대로 활용** — 빌더는 "어떤 지표를 어떤 가중치로?"의 UI일 뿐. 가중치 점수제가 빌딩 블록.

### 어려워지는 것
- Score 함수 정규화가 미묘 — 각 지표의 0~1 매핑이 합리적이어야 함 (특히 OBV 정규화)
- 가중치 + 임계값 디버깅 — 시그널 빈도 이상 시 어느 항목이 원인인지 분석 필요
- 사용자가 가중치 변경 시 백테스트 결과와 라이브 결과 불일치 가능 (캐시 무효화 필요)
- 신규 Settings 필드 ~9개 추가 (`bb_weight`, `cci_weight`, `sto_weight`, `obv_weight`, `buy_threshold`, `sell_threshold`, `sto_oversold`, `sto_overbought`, `obv_lookback`)

### 다시 검토해야 할 것
- 가중치 기본값 (BB 0.20 / CCI 0.20 / Sto 0.20 / OBV 0.40) — D+14 자기 보고에서 검증
- 임계값 0.65 기본 — 시그널 너무 많거나 적으면 조정
- Score 함수 정규화 방식 — 매매 스타일에 맞춰 monotonic curve 조정 (특히 OBV)
- V1 deprecate 일정 — Phase 2 이후 결정

### 위험 — 알파 탐색 트랩 회피

가중치 점수제는 "최적 가중치 찾기" 유혹이 강함. **[[feedback_signal_program_framing]] reinforce 정책 엄수:**

- 시스템이 "이 가중치가 최적"이라 추천 X
- 백테스트 결과는 사실 그대로 (Sharpe/MDD/win rate 숫자만) 표시
- 워크포워드 그리드 서치는 부가 옵션. 메인은 사용자가 가중치 정의 → 단일 백테스트
- "Best strategy" / "Recommended weights" 같은 UI 금지

## Action Items

### Pre-D+7 (Design 단계)
1. [ ] PRD `PRD_v2.1_phase1_strategy_v2.md` Open Questions OQ1/OQ2/OQ3에 "ADR-0010에서 해결됨" 표시
2. [ ] DESIGN.md §8.4 보강 초안 (Strategy 카탈로그 패턴 부록)
3. [ ] `docs/adr/README.md`에 ADR-0010 인덱스 추가

### D+7 GO/NO-GO 게이트
4. [ ] V1 운영 데이터 + 본인 자기 관찰로 본 ADR 결정 재검증 (product-lens)
5. [ ] GO 시: 본 ADR Status를 **Accepted**로 변경
6. [ ] 핸드오프 `handoff/v2.1.0_strategy_v2.md` 작성

### D+7 ~ D+14 (Week 1)
7. [ ] `compute_obv(candles) -> OBVSnapshot` 계산기 + 단위 테스트 (RED → GREEN)
8. [ ] `compute_stochastic_slow(candles, k_period, k_smooth, d_smooth) -> StochasticSnapshot` + 단위 테스트
9. [ ] DESIGN.md §8.2 IndicatorSnapshot에 신규 필드 추가 (시그니처 불변)

### D+14 ~ D+21 (Week 2)
10. [ ] Score 함수 4개 (BB/CCI/Sto/OBV) + 정규화 테스트 (0~1 범위, monotonic)
11. [ ] `FourIndicatorStrategy` 클래스 — Strategy Protocol 구현 + 가중치 합산 + 임계값 검사
12. [ ] `STRATEGY_CATALOG` registry + `get_strategy()` 헬퍼
13. [ ] Settings v2 신규 필드 9개 + 한국어 검증 메시지
14. [ ] 텔레그램 알림 `[V1]` / `[V2]` 태그

### D+21 ~ D+28 (Week 3)
15. [ ] 백테스트 `--strategy v2` 옵션
16. [ ] 워크포워드 `--strategy v2` 옵션
17. [ ] GUI 설정 페이지에 V2 전용 섹션 (mockup 참조: `mockups/v2.1_settings_preview.html`)
18. [ ] GUI 백테스트 비교 (mockup 참조: `mockups/v2.1_backtest_compare_preview.html`) — R_P1_1 P0 격상 여부 결정
19. [ ] 회귀 점검 — V1 동작 0건 영향
20. [ ] v2.1.0 tag + push + GitHub Release

### Post-D+28
21. [ ] D+35 사용자 자기 보고 — G3 "V2를 매매 결정에 실제로 사용?" YES/NO
22. [ ] D+42 Phase 2 GO/NO-GO (전략 빌더)

## Open Items (Phase 2~4)

| Phase | ADR | 내용 |
|---|---|---|
| 2 | ADR-0011 (예정) | 전략 DSL — 사용자 정의 지표 조합 |
| 3 | ADR-0012 (예정) | 멀티 타임프레임 (1H+4H+1D) — score 통합 방식 |
| 4 | ADR-0013 (예정) | 마켓별 N전략 할당 — score 통합 vs 별개 발사 |
| 5+ | ADR-0014 (예정) | 사용자 정의 지표 등록 (v4.0) |

## UI 패턴 재사용 (Phase 2 빌더 설계 시)

본 ADR 시점에 v2.1 mockup(`mockups/v2.1_settings_preview.html`)에 도입된 UI 패턴 — Phase 2 빌더 UI 설계에서 일관성 위해 재사용 검토:

| 패턴 | v2.1 사용처 | Phase 2 재사용 후보 |
|---|---|---|
| Preset chip + custom 입력 | 쿨다운 (1h/2h/4h/8h/24h + custom) | 가중치 슬라이더 옵션? 임계값 chip 0.55/0.65/0.75/0.85? |
| 4단 다중 선택 (검색 + chip + 빠른추가 + 전체목록) | 화이트리스트 | 빌더에서 사용자 정의 지표 선택 시 동일 패턴 |
| 토글 카드 (V1/V2) | 전략 모드 | Phase 2 빌더에서 strategy preset 카드로 |
| 영역 음영처리 (opacity 0.35) | V1 선택 시 V2 영역 | 빌더에서 비활성 옵션 안내 |

가중치 점수제는 Phase 2~4 모두에서 빌딩 블록으로 재사용. 본 ADR의 카탈로그 패턴 + 가중치 score 모델이 v3.0 전체의 핵심 인프라.

---

> **한 줄 요약:** OBV 신규 지표 + 가중치 점수제 (BB 0.20 / CCI 0.20 / Sto 0.20 / OBV 0.40, 임계값 0.65 기본, GUI 튜닝 가능) + Sto 15/85 엄격 임계값 + Module-level Strategy Registry. 사용자의 "거래량 중시 + 거짓 시그널 최소화 + 추세 추종 + 분할 매수" 매매 스타일에 정합. D+7 GO/NO-GO 후 D+28까지 구현. [[feedback_signal_program_framing]] reinforce 정책 엄수 — 시스템이 가중치 추천 X, 사용자가 정의.
