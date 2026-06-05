# 전략 확장 설계 — Fractal(암호화폐) + Donchian + RSI(2) (v2.3 제안)

**작성일** 2026-06-05 · **상태** 설계 확정, 구현 대기 (Claude Code)
**관련** [DESIGN.md §8.3](../DESIGN.md) (Strategy Protocol) · [ADR-0010](adr/0010-v2-strategy.md) · [ADR-0018](adr/) (KrFractal) · [ADR-0002](adr/0002-no-autotrading.md) (자동매매 금지 불변)

---

## 1. 배경과 선정 논리 (트레이더 관점)

현재 암호화폐 전략은 BB+CCI(V1)·4지표 가중치(V2) — 모두 **평균회귀 계열**이다.
평균회귀는 횡보장에서 강하지만 강한 추세장에서 연속 손실이 난다. 전략 추가의 목적은
"더 많은 신호"가 아니라 **시장 레짐 커버리지**다.

| 전략 | 레짐 | 성격 | 상태 |
|------|------|------|------|
| BB+CCI (V1) | 횡보·과열 반전 | 평균회귀 | 기존 |
| 4지표 가중 (V2) | 횡보+거래량 확인 | 평균회귀 변형 | 기존 (D+7 NO-GO, v1 운용 중) |
| **Williams Fractal (V3)** | 구조 전환·돌파 | 구조 돌파 | **국장용 기구현 → 암호화폐 개방** |
| **Donchian 20 돌파 (V4)** | 강한 추세 | 추세추종 (터틀식) | **신규** |
| **RSI(2) 평균회귀 (V5)** | 추세 중 단기 눌림 | 초단기 평균회귀 + 추세 필터 | **신규** |

선정 이유:
- **Donchian**: 추세추종의 원형. 규칙이 단순해 과최적화 여지가 적고, 평균회귀가
  죽는 구간(강추세)을 정확히 보완한다. 신규 지표 1개(채널)만 필요.
- **RSI(2) (Connors)**: "장기 추세 위에서 단기 과매도만 산다"는 규율이 내장된
  평균회귀. BB+CCI보다 호흡이 훨씬 짧아 겹치지 않는다. 매도(청산) 신호도 대칭으로 명확.
- 제외한 것: MACD(후행성, BB와 정보 중복), VWAP(24/7 암호화폐에 세션 앵커 부적합),
  TTM Squeeze(V1 모드 B와 중복).

## 2. 변경 범위 요약

```
src/signal_program/
├── indicators/
│   ├── fractal.py        # [이동] kr_fractal 내 fractal 계산을 공용 모듈로 추출 (또는 재사용)
│   ├── donchian.py       # [신규] Donchian 채널
│   └── rsi.py            # [신규] Wilder RSI
├── strategies/
│   ├── fractal.py        # [신규] FractalStrategy (KrFractalStrategy 로직 재사용/일반화)
│   ├── donchian.py       # [신규] DonchianStrategy
│   ├── rsi2.py           # [신규] Rsi2Strategy
│   └── __init__.py       # STRATEGY_CATALOG에 "v3","v4","v5" 등록
├── enums.py              # StrategyMode 멤버 추가 (아래 §5)
├── config.py / web/schemas.py / settings.html  # 파라미터 노출
```

**Hard Lines 준수**: `Strategy` Protocol(§8.3) 시그니처 그대로 구현(신규 클래스 추가는 허용).
`IndicatorSnapshot`은 **필드 추가만** (기존 필드 수정 금지). 자동매매 코드 없음.

## 3. 전략 명세

### 3.1 V3 — Williams Fractal 돌파 (암호화폐)

KrFractalStrategy(ADR-0018)의 로직을 마켓 중립으로 일반화한다. 국장 전용 가정
(타임프레임 추론 등)만 분리하고 **프랙탈 확정 규칙은 동일**: n번째 봉의 프랙탈은
n+2 봉 마감 후 확정 (5봉 패턴, 미래 참조 금지).

- **매수**: 종가가 최근 확정 up-fractal 고점 상향 돌파 + `volume_ratio ≥ fractal_volume_threshold`(기본 1.2)
- **매도**: 종가가 최근 확정 down-fractal 저점 하향 돌파 + 동일 거래량 필터
- **STRONG**: `volume_ratio ≥ fractal_volume_strong`(기본 2.0)
- **파라미터**: `fractal_volume_threshold`, `fractal_volume_strong`, `fractal_max_age`(확정 프랙탈 유효 봉 수, 기본 20)

### 3.2 V4 — Donchian 20 돌파 (터틀식 추세추종)

- **지표**: `donchian(high, low, period) -> DataFrame(dc_upper, dc_lower, dc_middle)`
  - `dc_upper[t] = max(high[t-period .. t-1])` — **현재 봉 제외** (자기충족 방지, 봉 마감 기준)
- **매수**: 종가 > 직전 20봉 최고가 (`close > dc_upper`)
- **매도**: 종가 < 직전 10봉 최저가 (`close < dc_lower_exit`) — 터틀 관례: 진입보다 짧은 청산 채널
- **STRONG**: 돌파 + `volume_ratio ≥ donchian_volume_strong`(기본 1.5)
- **파라미터**: `donchian_entry_period`(기본 20), `donchian_exit_period`(기본 10), `donchian_volume_strong`(기본 1.5)
- **트레이더 노트**: 거래량 필터를 진입 조건에 넣지 않는다. 추세추종은 신호를 거르는 게 아니라
  손절을 짧게 가져가는 전략이다. 거래량은 강도 표시에만 쓴다.

### 3.3 V5 — RSI(2) 평균회귀 (Connors 변형)

- **지표**: `rsi(close, period) -> Series` — **Wilder 평활** (EMA α=1/period). SMA 방식 금지 (값이 달라짐)
- **추세 필터**: `sma(close, 200)` — 1시간봉 200기간 ≈ 8.3일
- **매수**: `close > sma200` **and** `rsi2 < rsi2_oversold`(기본 10)
- **매도**: `close < sma200` **and** `rsi2 > rsi2_overbought`(기본 90) — 하락 추세에서 단기 과열 = 매도 신호
- **STRONG**: rsi2 < 5 (또는 > 95)
- **파라미터**: `rsi2_period`(기본 2), `rsi2_oversold`(기본 10), `rsi2_overbought`(기본 90), `rsi2_trend_period`(기본 200)
- **트레이더 노트**: 추세 필터가 이 전략의 전부다. 필터 없는 RSI(2)는 하락장에서 계좌를 갈아먹는다.
  200 SMA 계산에 캔들 200개+ 필요 — 데이터 부족 시 신호 미발생(예외 아님)을 테스트로 보장할 것.

## 4. 공통 규칙 (기존 도메인 규칙 승계)

- 모든 평가는 **마감 봉 close 기준**, 진행 중 봉 제외
- KST timezone-aware datetime
- 신호는 알림 전용 — 주문 실행 코드 절대 금지 (ADR-0002)
- 쿨다운·화이트리스트 등 운영 파라미터는 기존 메커니즘 그대로 적용

## 5. 등록·노출 설계

### enums.StrategyMode
기존 A/B/C/D에 추가: `DONCHIAN_BREAKOUT = "E"`, `RSI2_REVERSION = "F"`.
(FRACTAL_BREAKOUT = "D"는 기존 멤버 재사용 — 암호화폐 fractal도 D로 발신)

### STRATEGY_CATALOG (strategies/__init__.py)
```python
STRATEGY_CATALOG = {
    "v1": _build_v1,            # 기존
    "v2": FourIndicatorStrategy, # 기존
    "v3": _build_fractal,        # 신규
    "v4": _build_donchian,       # 신규
    "v5": _build_rsi2,           # 신규
}
```

### config.py
`strategy_version: Literal["v1","v2","v3","v4","v5"]` 확장 + §3 파라미터 필드
(범위 검증 포함: period 2~500, threshold 0~100 등).

### 설정 UI (settings.html / web/schemas.py / settings.js)
- 전략 선택 라디오 → 5개로 확장. 각 라디오에 한 줄 설명(레짐) 병기:
  - V1 BB+CCI (평균회귀) / V2 4지표 (가중 평균회귀) / V3 프랙탈 (구조 돌파) / V4 Donchian (추세추종) / V5 RSI2 (단기 평균회귀)
- 선택된 전략의 파라미터 섹션만 활성화 (기존 `v2-section dimmed` 패턴 재사용)
- 신규 파라미터는 지표 아코디언 패턴으로 추가, `settings.js`의 `INT_FIELDS`/`FLOAT_FIELDS` 등록 필수
- `id`/`name`/`data-field`/`err-{field}` 규칙 준수 (docs/ui/README.md §3.1)

### MODE_LABEL (dashboard.js)
`E: 'Donchian'`, `F: 'RSI2'` 추가. (D는 기존 '프랙탈' 재사용)

### IndicatorSnapshot 추가 필드 (전부 `| None = None`)
```python
dc_upper: float | None = None
dc_lower: float | None = None
rsi2: float | None = None
trend_sma: float | None = None
```

## 6. 백테스트 통합

기존 backtest 파이프라인이 Strategy Protocol을 받으므로 카탈로그 등록만으로 동작해야 한다.
지시문에 "백테스트 CLI에서 `--strategy v4` 식 선택이 가능한지 확인, 불가하면 mode 매핑 추가"를 포함.

**운용 전 의무 절차** (PRD 프레임: 사용자가 결정, 시스템은 계산기):
새 전략은 백테스트 → 워크포워드 → 소액 알림 관찰 순으로 사용자가 직접 검증 후 채택.
시스템은 수치만 보여준다. 기본 운용 전략은 v1 유지.

## 7. 테스트 요구 (TDD ★★★ — RED→GREEN→REFACTOR 의무)

전략 로직은 금전 관련 코어이므로 RED 테스트 먼저:

- `test_donchian_indicator.py`: 채널값 수계산 검증(소형 고정 배열), 현재 봉 제외 확인, NaN 구간
- `test_strategy_donchian.py`: 돌파 시 매수 / 청산채널 하향 시 매도 / 돌파 없으면 무신호 / STRONG 거래량 조건 / 진행 중 봉 미사용
- `test_rsi_indicator.py`: Wilder RSI 알려진 값 검증 (참조값 하드코딩), period=2 동작
- `test_strategy_rsi2.py`: 추세 필터 위+과매도=매수 / 필터 아래+과매도=무신호(핵심!) / 데이터<200 무신호 / STRONG 경계
- `test_strategy_fractal_crypto.py`: KRW- 마켓에서 KrFractal과 동일 패턴 입력 시 동일 신호 (회귀 보장)
- Hypothesis property 테스트: 기존 `test_strategy_bb_cci.py` 패턴 준수

## 8. 비목표

- 다중 전략 동시 운용 (현행 단일 선택 유지 — 별도 결정 필요)
- 국장(KIS) 쪽 전략 변경 (kr_strategy는 그대로)
- 포지션 사이징·피라미딩 (터틀 원본의 자금관리 부분 — 자동매매 금지 영역과 인접하므로 제외)
- 파라미터 자동 최적화 (사용자가 백테스트로 직접 조절)
