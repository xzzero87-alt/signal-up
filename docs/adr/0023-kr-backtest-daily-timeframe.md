# ADR-0023: 국장 백테스트 일봉 채택 — KIS 일봉 엔드포인트 추가, 라이브 전환은 엣지 게이트 후

**Date**: 2026-06-16
**Status**: accepted
**Deciders**: xzzero87

## Context

ADR-0022 Phase 1은 국장 전략의 수익 엣지 검증을 요구한다. 그러나 국장은 백테스트 산출물이 **0건**이다 — `strategy_matrix.csv`·워크포워드는 전부 코인(BTC/ETH/XRP)이고, 백테스트 엔진에 KR 데이터 ingest 경로가 없다.

원인 조사 결과, 이미 연동된 KIS에서 쓰는 분봉 엔드포인트(`inquire-time-itemchartprice`, 적용됨)는 **당일 장중 데이터만** 반환해 과거 분봉을 못 받는다. 라이브 국장 전략(`KrFractalStrategy`, ADR-0018)은 120분봉으로 동작하므로, 라이브 타임프레임 그대로는 과거 데이터를 무료로 확보할 길이 사실상 없다(키움/대신 COM API는 Windows 전용·1~2년 한정·무거움).

반면 **일봉**은 같은 KIS 계정의 다른 엔드포인트(`inquire-daily-itemchartprice`, FHKST03010100, 미적용)로 100영업일/호출 + 페이지네이션해 수년치 확보가 가능하다. `KrFractalStrategy`는 캔들 DataFrame만 받는 **타임프레임 비종속** 구조라 일봉에 코드 변경 없이 적용된다.

## Decision

국장 백테스트는 **일봉(daily)** 기준으로 한다. 데이터는 신규 벤더 없이 이미 연동된 KIS의 **일봉 엔드포인트(`inquire-daily-itemchartprice`)**를 추가해 조달하고, `KrFractalStrategy`를 일봉 캔들에 그대로 적용한다.

라이브 국장 신호는 당분간 **120분봉을 유지**한다. 일봉 백테스트가 ADR-0022의 엣지 합격 기준을 통과하면 그때 라이브를 일봉으로 전환하고 ADR-0018을 supersede한다. **현 시점에는 ADR-0018을 변경하지 않는다** (ADR-0017의 "검증 전 라이브 미변경" 원칙과 정합).

## Alternatives Considered

### Alternative 1: 라이브·백테스트 즉시 일봉 통일
- **Pros**: 검증=운용이 처음부터 일치, 단계 단순.
- **Cons**: 엣지 미확인 상태에서 라이브를 먼저 바꾸는 셈.
- **Why not**: ADR-0017·0022의 엣지-우선 원칙 위반. 전환은 게이트 통과 후로 미룬다.

### Alternative 2: 120분봉 유지 + 키움/대신 COM으로 과거 분봉 확보
- **Pros**: 라이브와 백테스트 타임프레임 완전 일치.
- **Cons**: Windows COM 전용 통합이 무겁고, 깊이 1~2년 한정, KIS와 별도 데이터 경로.
- **Why not**: 엣지를 "있는지 없는지" 먼저 확인하는 비용으로 과하다. 일봉이 압도적으로 빠르다.

### Alternative 3: pykrx / FinanceDataReader로 일봉 조달
- **Pros**: 호출이 더 단순할 수 있음, KRX 공식 OHLCV.
- **Cons**: 신규 의존성 추가. KIS는 이미 있음.
- **Why not**: 같은 KIS로 해결되면 의존성 중복 금지(CLAUDE.md). 단, KIS 일봉 페이지네이션·조정주가 처리 부담이 예상보다 크면 이 대안을 재검토한다.

## Consequences

### Positive
- 국장 엣지를 "표본 0 → 측정 가능"으로 최소 비용에 전환.
- 같은 KIS 키 재사용 — 신규 벤더·신규 의존성 0.
- 전략 코드 불변(`KrFractalStrategy` 타임프레임 비종속). §8.1~8.5 `Candle` 시그니처도 그대로(일봉도 동일 모델).

### Negative
- 검증 기간 동안 백테스트(일봉)와 라이브(120분봉)가 불일치 — 일봉 결과는 "일봉 전략의 엣지"이지 현재 라이브의 직접 검증은 아니다.
- 게이트 통과 시 "라이브 일봉 전환"이라는 후속 단계가 추가로 필요.

### Risks
- **일봉 신호 빈도 ↓ → 거래 표본 부족** → 유니버스 43종 전체 × 장기간으로 표본 확보, 통계 유의성 미달 구간은 결론 보류.
- **조정주가 정확성** → KIS `FID_ORG_ADJ_PRC`로 액면분할·배당 조정 일관 적용, pykrx와 표본 교차검증.
- **구현 범위** → `Timeframe`에 `DAY` 값 추가 필요(기존 값 수정 아님, 허용된 신규 값). `_infer_timeframe`·캔들 ingest 일봉 분기 배선.

## 관련 자료

- [ADR-0022](0022-post-v24-roadmap-edge-first.md) — 엣지-우선 로드맵(Phase 1 게이트)
- [ADR-0018](0018-kr-fractal-strategy.md) — 국장 KrFractal 전략(라이브 120분봉, 게이트 통과 시 supersede 대상)
- [ADR-0017](0017-v2-strategy-no-go-redesign.md) — 검증 전 라이브 미변경 원칙
- [ADR-0016](0016-kis-api-korean-stock-datasource.md) — KIS API 데이터 소스 채택
- `src/signal_program/exchanges/kis_api.py` — 현재 분봉 엔드포인트(당일 한정)
- KIS 일봉 API: `inquire-daily-itemchartprice` (TR `FHKST03010100`)
