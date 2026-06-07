# Claude Code 지시문 — 전략 확장 v2.3 (Fractal 개방 + Donchian + RSI2)

> 사용법: 아래 블록을 Claude Code CLI에 그대로 붙여넣기.
> 설계 근거: [`../strategy-expansion-v2.3.md`](../strategy-expansion-v2.3.md) — 막히면 이 문서로 돌아와 결정 확인.

```
docs/strategy-expansion-v2.3.md 를 읽고 전략 확장을 구현해줘.
TDD 등급 ★★★ — 모든 전략·지표 로직은 RED→GREEN→REFACTOR 순서를 지켜.
커밋도 RED/GREEN/REFACTOR 단위로 분리해줘.

## 단계 1 — 지표 (RED 먼저)

1. tests/unit/test_donchian_indicator.py 작성 (실패 확인):
   - 고정 배열로 dc_upper/dc_lower 수계산 검증
   - dc_upper[t]는 high[t-period..t-1] — **현재 봉 제외** 확인
   - 데이터 < period 구간은 NaN
2. src/signal_program/indicators/donchian.py 구현 (GREEN):
   - def donchian(high: pd.Series, low: pd.Series, period: int = 20) -> pd.DataFrame
   - 반환 컬럼: dc_upper, dc_lower, dc_middle. pandas/numpy만 사용.
3. tests/unit/test_rsi_indicator.py 작성 (실패 확인):
   - Wilder 평활 RSI — 참조값 하드코딩 검증 (예: 표준 14기간 예제 데이터)
   - period=2 정상 동작
4. src/signal_program/indicators/rsi.py 구현 (GREEN):
   - def rsi(close: pd.Series, period: int = 14) -> pd.Series
   - Wilder 평활 (ewm(alpha=1/period, adjust=False)). SMA 방식 금지.

## 단계 2 — IndicatorSnapshot 필드 추가

models.py IndicatorSnapshot에 추가 (전부 Optional, 기존 필드 수정 금지):
  dc_upper: float | None = None
  dc_lower: float | None = None
  rsi2: float | None = None
  trend_sma: float | None = None

## 단계 3 — 전략 (각각 RED 먼저)

설계서 §3 명세 그대로. 각 전략은 Strategy Protocol(base.py) 구현:
  name 속성 + def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]

3a. FractalStrategy (src/signal_program/strategies/fractal.py):
   - KrFractalStrategy의 프랙탈 확정 로직 재사용 — 공용 함수로 추출하거나 위임.
     국장 전용 가정(타임프레임 추론 등)은 가져오지 말 것.
   - tests/unit/test_strategy_fractal_crypto.py: KrFractal과 동일 패턴 입력 시
     동일 신호(회귀 보장), 미확정 프랙탈 미사용, 거래량 필터, STRONG 경계
   - StrategyMode.FRACTAL_BREAKOUT ("D") 재사용

3b. DonchianStrategy (src/signal_program/strategies/donchian.py):
   - 매수: close > dc_upper(entry_period=20) / 매도: close < dc_lower(exit_period=10)
   - STRONG: volume_ratio >= donchian_volume_strong(1.5)
   - enums.StrategyMode에 DONCHIAN_BREAKOUT = "E" 추가
   - tests/unit/test_strategy_donchian.py: 설계서 §7 케이스 전부

3c. Rsi2Strategy (src/signal_program/strategies/rsi2.py):
   - 매수: close > sma200 AND rsi2 < 10 / 매도: close < sma200 AND rsi2 > 90
   - STRONG: rsi2 < 5 또는 > 95
   - 캔들 < trend_period+1 이면 신호 없음 (예외 금지) — 테스트 필수
   - enums.StrategyMode에 RSI2_REVERSION = "F" 추가
   - tests/unit/test_strategy_rsi2.py: 특히 "필터 아래+과매도=무신호" 케이스

## 단계 4 — 등록·설정·UI

- strategies/__init__.py STRATEGY_CATALOG에 "v3","v4","v5" 등록
- config.py: strategy_version Literal 확장 + 설계서 §3 파라미터 (범위 검증)
- web/schemas.py: SettingsView/SettingsUpdate에 동일 파라미터 (마스킹 불필요, 숫자만)
- web/help_text.py: 신규 파라미터 도움말
- settings.html (현재 구조에 맞춰 — M20에서 재설계됨, 주의):
  - 전략 선택은 라디오가 아니라 "전략 카드" 그리드다. 지금 V3/V4/V5는
    `<div class="strat-card" style="opacity:.45;cursor:default" title="...구현 대기">`
    로 비활성 처리돼 있다. 이 3개를 V1/V2와 동일한 형태로 바꿀 것:
    `<label class="strat-card" id="card-v3">` + 내부에
    `<input type="radio" name="strategy_version" value="v3" onchange="pickStrategy('v3')">`
    (회색 인라인 style 제거).
  - 각 전략의 파라미터는 별도 `<div class="active-params" id="v{N}-params">`로 추가하고,
    기본은 `style="display:none"`. 선택된 전략 것만 보이게 한다.
  - 인라인 `<script>`의 `pickStrategy(v)` 함수를 5개 전략 모두 처리하도록 확장:
    카드 5개의 .on 토글 + params 박스 5개의 display 전환. `updateV2Dim()`(저장 후
    refreshForm이 호출하는 훅)도 같은 로직으로 맞출 것.
  - docs/ui/README.md §3.1 규칙 준수: 모든 입력에 id/name/data-field/err-{field} 유지.
  - settings.js의 INT_FIELDS/FLOAT_FIELDS Set에 신규 숫자 필드 등록(필수).
  - app.css 캐시 버전(base.html/index.html/settings.html의 ?v=mNN)을 한 단계 올릴 것.
- static/js/dashboard.js: MODE_LABEL에 E: 'Donchian', F: 'RSI2' 이미 추가됨(확인만).
  STRATEGY_LABEL(상태 패널 운용현황 카드)에 v3/v4/v5 라벨 추가 필요.
- 백테스트 CLI가 신규 전략 선택 가능한지 확인, 불가하면 매핑 추가

## 단계 5 — 게이트

uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/        # strict
uv run pytest --cov=src/ --cov-fail-under=70
uv run python scripts/ui_check.py   # UI 변경분 검증

## 금지

- 자동매매·주문 코드 (ADR-0002)
- DESIGN.md §8.1~8.5 기존 시그니처 수정
- KrFractalStrategy 동작 변경 (국장 회귀 깨짐 금지 — 기존 테스트 그대로 통과해야 함)
- 진행 중(미마감) 봉 사용
- 파라미터 자동 최적화 로직

## 산출물

1. 변경/생성 파일 목록과 이유
2. RED→GREEN 커밋 로그
3. 게이트 4종 통과 출력
4. 신규 전략 3종 백테스트 1회씩 실행 결과 (KRW-BTC, 최근 6개월)
```
