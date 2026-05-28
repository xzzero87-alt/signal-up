# ADR-0018: 국내 주식 시그널 전략 — Williams Fractal 기반 (`KrFractalStrategy`)

**Date**: 2026-05-28
**Status**: accepted
**Deciders**: 프로젝트 오너

## Context

`kr_runner.py`(ADR-0015)와 KIS API 어댑터(ADR-0016)로 국내 주식 스캔 루프는 완성됐다.
그러나 현재 `KrStockRunnerService`에 주입되는 `strategy: Strategy`가 기존 `BbCciStrategy`(업비트용)를
그대로 사용하고 있어 국내 주식 특성에 맞는 전략이 없는 상태다.

국내 주식(KOSPI/KOSDAQ)은 암호화폐와 달리 (1) 평일 09:00~15:30 단기 세션, (2) 기관·외인 수급 영향으로
추세 지속성이 강하며, (3) 거래량 급증 시 방향성이 선명하다. 이 특성에 맞는 지표로
**Williams Fractal**을 채택한다. 프랙탈은 가격의 국소 고점(저항)·저점(지지)을 5봉 패턴으로 식별하고,
해당 레벨을 돌파할 때 추세 전환 또는 추세 가속 시그널로 해석한다.

## Decision

국내 주식 전용 전략 `KrFractalStrategy`를 `strategies/kr_fractal.py`에 신규 구현한다.
`Strategy` Protocol(`strategies/base.py`)을 구현하며, 기존 `BbCciStrategy` 코드는 변경하지 않는다.

**모드 D — Fractal Breakout (핵심 모드)**: 확정된 프랙탈 레벨을 종가가 돌파하고 거래량이 임계값 이상이면 시그널 발생.

`config.py`에 `kr_strategy` 설정값을 추가하고, `signal serve` 기동 시 `kr_strategy == "fractal"`이면
`KrFractalStrategy`를 `KrStockRunnerService`에 주입한다.

## 핵심 알고리즘

### Williams Fractal 정의 (5봉 패턴)

```
Up Fractal (저항): df['high'][n] > df['high'][n-1] AND
                   df['high'][n] > df['high'][n-2] AND
                   df['high'][n] > df['high'][n+1] AND
                   df['high'][n] > df['high'][n+2]

Down Fractal (지지): df['low'][n] < df['low'][n-1] AND
                     df['low'][n] < df['low'][n-2] AND
                     df['low'][n] < df['low'][n+1] AND
                     df['low'][n] < df['low'][n+2]
```

봉 마감 기준 평가이므로, 위치 `n`의 프랙탈은 `n+2` 봉이 마감된 뒤 확정된다.
실시간 DataFrame에서 **가장 최근 확정 프랙탈**은 `df.iloc[-3]`이 n이 되는 위치다.

### 시그널 조건 (Mode D — `StrategyMode.FRACTAL_BREAKOUT`)

```
BUY:  close[-1] > nearest_confirmed_up_fractal_high
      AND volume_ratio[-1] >= fractal_volume_threshold
      AND nearest_confirmed_up_fractal_age <= fractal_lookback

SELL: close[-1] < nearest_confirmed_down_fractal_low
      AND volume_ratio[-1] >= fractal_volume_threshold
      AND nearest_confirmed_down_fractal_age <= fractal_lookback
```

### 시그널 강도

| 조건 | 강도 |
|------|------|
| `volume_ratio >= fractal_volume_strong` | `STRONG` |
| 그 외 BUY/SELL 조건 충족 | `NORMAL` |

### 파라미터 (설정 가능)

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `fractal_lookback` | `100` | 프랙탈 탐색 최대 봉 수 |
| `fractal_volume_threshold` | `1.2` | 거래량 배율 하한 (normal) |
| `fractal_volume_strong` | `2.0` | 거래량 배율 하한 (strong) |

## 필요한 코드 변경

### 1. `enums.py` — `StrategyMode` 신규 값 추가 (기존 값 변경 없음)
```python
FRACTAL_BREAKOUT = "D"   # KrFractalStrategy 모드 D
```

### 2. `models.py` — `IndicatorSnapshot`에 프랙탈 필드 추가 (선택적, 기존 필드 변경 없음)
```python
fractal_up: float | None = None      # 가장 최근 확정 Up Fractal 레벨
fractal_down: float | None = None    # 가장 최근 확정 Down Fractal 레벨
fractal_up_age: int | None = None    # Up Fractal 이후 경과 봉 수
fractal_down_age: int | None = None  # Down Fractal 이후 경과 봉 수
```

### 3. `strategies/kr_fractal.py` — 신규 파일
```python
class KrFractalStrategy:
    name: str = "kr_fractal_v1"

    def __init__(
        self,
        fractal_lookback: int = 100,
        fractal_volume_threshold: float = 1.2,
        fractal_volume_strong: float = 2.0,
    ) -> None: ...

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]: ...

    @staticmethod
    def _find_fractals(df: pd.DataFrame, lookback: int) -> tuple[float | None, int, float | None, int]:
        """(up_fractal_level, up_age, down_fractal_level, down_age) 반환."""
        ...
```

### 4. `config.py` — `Settings`에 필드 추가
```python
kr_strategy: Literal["bb_cci", "fractal"] = "fractal"
fractal_lookback: int = 100
fractal_volume_threshold: float = 1.2
fractal_volume_strong: float = 2.0
```

### 5. `cli.py` — `signal serve` 기동 시 전략 선택 분기
```python
if settings.kr_strategy == "fractal":
    kr_strategy = KrFractalStrategy(
        fractal_lookback=settings.fractal_lookback,
        fractal_volume_threshold=settings.fractal_volume_threshold,
        fractal_volume_strong=settings.fractal_volume_strong,
    )
else:
    kr_strategy = BbCciStrategy(...)  # 기존 fallback
```

## Alternatives Considered

### Alternative 1: BbCciStrategy 업비트 전략 그대로 사용
- **Pros**: 구현 비용 0, 즉시 사용 가능
- **Cons**: BB+CCI는 24/7 변동성 장에 맞게 튜닝됨. 국내 주식의 짧은 세션·추세 특성에 맞지 않아 false signal 과다 예상
- **Why not**: 전략과 시장 특성의 불일치. 별도 전략 필요.

### Alternative 2: Williams Fractal + Alligator 조합 (Bill Williams 원안)
- **Pros**: Alligator(3 이동평균 조합)로 추세 방향 필터 추가 → 정확도 향상
- **Cons**: 파라미터 6개 이상, 구현 복잡도 대폭 증가; 백테스트 없이 파라미터 결정 불가
- **Why not**: v1은 단순하게 시작. Alligator는 백테스트 결과 보고 v2에서 검토.

### Alternative 3: RSI + MACD (Node.js 프로토타입 방식)
- **Pros**: `korean_stock_signal/` 프로토타입에서 이미 구현됨, 이식 빠름
- **Cons**: RSI·MACD 조합은 업비트 V2 전략과 유사 방향 (지표 중복). V2가 NO-GO 판정을 받은 이후 같은 계열 지표를 반복할 이유 없음
- **Why not**: 다른 계열 지표(가격 구조 기반 Fractal)로 다각화.

### Alternative 4: 수급 점수 기반 (기관·외인 매매 동향)
- **Pros**: 국내 주식 특유의 기관·외인 수급 데이터 활용 가능
- **Cons**: KIS Open API 무료 플랜에서 수급 데이터 실시간 제공 불명확; 데이터 신뢰성·지연 검증 필요
- **Why not**: 데이터 가용성 미검증. 기술지표 기반 v1 안정화 후 검토.

## Consequences

### Positive
- 국내 주식 특성(추세 지속, 거래량 급증)에 적합한 전략 확보
- 기존 `Strategy` Protocol 구현 → `KrStockRunnerService` 코드 변경 없음
- `BbCciStrategy`와 완전히 분리된 코드베이스 → 독립 테스트 가능
- `IndicatorSnapshot` 신규 필드(`fractal_up/down`)로 GUI 대시보드에 프랙탈 레벨 표시 가능

### Negative
- `StrategyMode.FRACTAL_BREAKOUT("D")` 신규 enum 값 추가 → GUI·텔레그램 메시지 레이블 처리 필요
- 국내 주식 백테스트가 아직 없어 파라미터 기본값의 근거가 경험적 추정 수준
- 5봉 패턴 확인에 최소 5개 캔들 필요 → 데이터 부족 시 시그널 없음

### Risks
- **프랙탈 중복 돌파**: 같은 프랙탈 레벨을 여러 봉에 걸쳐 반복 돌파 시 중복 시그널 → 쿨다운(`CooldownStore`)으로 완화
- **파라미터 과최적화**: 백테스트 없는 기본값 사용 → D+14 이후 워크포워드 검증 권장 (ADR-0017 패턴)
- **프랙탈 고령화**: `fractal_lookback=100` 이내에 프랙탈이 없으면 시그널 발생 안 함 → 루프에서 `INFO` 로그로 기록

## 구현 시 TDD 적용 가이드

```
RED:   5봉 패턴 합성 데이터로 _find_fractals 단위 테스트 작성
GREEN: _find_fractals 구현
RED:   BUY/SELL 시그널 조건 + 강도 시나리오 테스트 (≥10종)
GREEN: evaluate() 구현
RED:   쿨다운 통합, 볼륨 미달 no-signal 시나리오
GREEN: 전체 통과
```

## 관련 자료

- [ADR-0015](0015-korean-stock-market-support.md) — 국내 주식 시장 지원 추가
- [ADR-0016](0016-kis-api-korean-stock-datasource.md) — KIS API 데이터 소스
- [ADR-0017](0017-v2-strategy-no-go-redesign.md) — V2 전략 NO-GO — 단순 지표 기반 v1 유지 원칙
- [ADR-0010](0010-strategy-catalog.md) — Strategy 카탈로그 패턴 (신규 전략 등록 방식)
- [`strategies/kr_fractal.py`](../../src/signal_program/strategies/kr_fractal.py) — 구현 예정
