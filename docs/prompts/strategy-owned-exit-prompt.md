# Claude Code 지시문 — ADR-0021 구현: v4 Donchian 고유 청산 (SupportsExit)

> **작성:** 2026-06-11 Cowork 설계 세션
> **배경:** 전략 비교 매트릭스에서 v4가 진입 신호 품질 최상위. 단 24봉 시간 청산으로만 평가된
> 상태라, 고유 청산(`donchian_exit_period` 채널) 포함 재평가가 목적.
> **설계 결정:** `docs/adr/0021-strategy-owned-backtest-exit.md` — **먼저 정독할 것.**
> **선행 숙지:** `CLAUDE.md` 변경 금지 영역. Strategy Protocol 기존 시그니처 무수정 (신규 보조 Protocol만 추가).

---

## Task 0 — ADR-0021 승격

- `docs/adr/0021-strategy-owned-backtest-exit.md` Status: `proposed` → `accepted`
- `docs/adr/README.md` 인덱스 표에 0021 행 추가

## Task 1 — 엔진 청산 위임 (TDD ★★★)

### RED

`tests/unit/test_backtest_engine.py`에 추가 (기존 `_MockStrategy` 패턴):

1. `should_exit`가 보유 k봉째(k < 24)에 True를 반환하는 mock → 트레이드 `bars_held == k`
   (현재 엔진은 위임이 없으므로 24봉까지 끌고 가서 실패해야 정상 — RED 입증)
2. `should_exit`가 항상 False인 mock → `bars_held == max_holding_bars` (캡 유지 확인)
3. `SupportsExit` 미구현 mock + 유효한 `bb_middle` → 기존 타깃 청산 그대로 (회귀 가드)

### GREEN

- `strategies/base.py`: `SupportsExit` 신규 추가 (ADR-0021의 시그니처 그대로, `@runtime_checkable`)
- `backtest/engine.py` 포지션 보유 분기에서:
  - `isinstance(self.strategy, SupportsExit)`이면 → 청산 = `should_exit(...) or 캡 or stop_loss`
    (BB 중심선 타깃은 **미적용**)
  - 아니면 → 기존 로직 그대로 (`bb_middle > 0` 가드 포함, 한 줄도 변경 금지)
- isinstance 판정은 포지션 진입 시 1회만 해서 변수로 캐시 (매 봉 isinstance 비용 회피)

### REFACTOR / 문서 동기화

- `engine.py` 모듈 docstring §6.1에 위임 규칙 한 줄: "SupportsExit 구현 전략은 청산 위임, 캡 유지"
- `DESIGN.md` §6.1에 동일 단서 추가

## Task 2 — DonchianStrategy.should_exit 구현 (TDD ★★★)

### 규칙 (ADR-0021)

직전 `donchian_exit_period`봉(현재 봉 **제외**)의 최저 `low`보다 현재 봉 `close`가 낮으면 청산:

```python
window = candles.iloc[-(self.exit_period + 1) : -1]  # 현재 봉 제외 직전 N봉
return float(candles.iloc[-1]["close"]) < float(window["low"].min())
```

- 봉 수가 `exit_period + 1` 미만이면 False (청산 판단 불가 → 캡에 맡김)
- 진입 직후 봉부터 판단 대상 (entry_bar_idx 이전 데이터도 채널 계산에 포함 — 터틀 컨벤션)

### 테스트 (합성 캔들)

- 채널 하향 마감 시 True / 채널 위에서 False / 봉 부족 시 False — 경계 3건
- `isinstance(DonchianStrategy(...), SupportsExit)` 참 확인 (runtime_checkable 동작 가드)

## Task 3 — 매트릭스 재실행 및 기록

1. 기존 CSV 백업: `reports/compare/strategy_matrix.csv` → `strategy_matrix_time_exit.csv`
2. `powershell -ExecutionPolicy Bypass -File scripts\strategy_matrix.ps1`
3. **무결성 체크:**
   - v4 `avg_bars_held`: 24.0 고정 → 분포로 변할 것. **24 근처에 몰리면 캡 바인딩 의심** — 수치만 기록
   - v1/v3/v5 칸: `strategy_matrix_time_exit.csv`와 동일할 것 (위임 분기 회귀 없음)
4. 결과 **해석 금지** — Cowork 세션 몫

## 범위 제한 (하지 말 것)

- v3/v5의 should_exit 구현 (YAGNI — ADR-0021 결정)
- max_holding_bars 캡 값 변경 (몰림이 보이면 보고만)
- walkforward 쪽 코드 (별도 핸드오프 `walkforward-v4-prompt.md`)

## 완료 기준 (품질 게이트)

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] RED 입증 → GREEN (신규 + 기존 엔진 테스트 전부 통과)
- [ ] 재실행 무결성 체크 2건 통과 (v4 변화 / v1·v3·v5 불변)
- [ ] `CHANGELOG.md` Unreleased 항목 추가
- [ ] 커밋 분리: ① ADR 승격+인덱스, ② SupportsExit+엔진 위임+테스트, ③ Donchian 청산+재실행 산출물

## 세션 시작 명령

```powershell
cd C:\Users\user3\Desktop\VibeCoding\signal-up
claude "docs/prompts/strategy-owned-exit-prompt.md 를 읽고 그대로 수행해줘"
```
