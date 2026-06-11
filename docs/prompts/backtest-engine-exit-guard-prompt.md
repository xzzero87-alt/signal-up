# Claude Code 지시문 — 백테스트 엔진 청산 가드 (v3/v4/v5 1봉 청산 버그 수정)

> **작성:** 2026-06-10 Cowork 세션 (전략 비교 매트릭스 결과 검증 중 발견)
> **배경:** 5전략 × 5구간 × 3마켓 비교 매트릭스(`scripts/strategy_matrix.ps1`, 75런) 실행 결과,
> v3/v4/v5의 45칸이 엔진 버그로 전부 무효 판정. 설계 문서: `시그널 프로그램/plans/strategy-comparison-matrix.md`
> **선행 숙지:** `CLAUDE.md` 변경 금지 영역 — DESIGN.md §8.1~8.5 도메인 시그니처 불변, 자동매매 코드 금지.

---

## 컨텍스트 — 버그 진단 (Cowork에서 확인 완료)

`src/signal_program/backtest/engine.py`의 청산 조건 (line ~91):

```python
should_exit = bars_held >= self.max_holding_bars or close >= bb_middle or hit_sl
```

`bb_middle`은 진입 시그널의 `IndicatorSnapshot.bb_middle`에서 가져오는데, **비-BB 전략은 이 값을 0.0으로 채운다**:

- `src/signal_program/strategies/donchian.py:125` — `bb_middle=0.0`
- `src/signal_program/strategies/fractal.py:138` — `bb_middle=0.0`
- `src/signal_program/strategies/rsi2.py:135` — `bb_middle=0.0`

`close >= 0.0`은 항상 참 → v3/v4/v5의 **모든 포지션이 1봉 만에 청산**된다.

**증거:** `reports/compare/strategy_matrix.csv`에서 v3/v4/v5의 `avg_bars_held`가 75칸 전부 정확히 `1.0`
(v1은 12.9~14.5). 결과적으로 v3/v4/v5 칸은 "다음 봉 시가 진입 → 같은 봉 종가 청산 + 왕복 0.2% 비용"의
반복일 뿐, 전략 성과가 아니다.

---

## Task 1 — 엔진 청산 가드 추가

**TDD 등급: ★★★ (RED → GREEN → REFACTOR)**

### RED

`tests/unit/test_backtest_engine.py`에 테스트 추가 (기존 `_MockStrategy` 패턴 재사용,
`test_i_24bar_max_hold_without_bb_exit` 컨벤션 참고):

- mock 전략이 `bb_middle=0.0`인 시그널을 1회 발생 → 엔진 실행
- **기대:** 해당 트레이드의 `bars_held == max_holding_bars` (타깃 청산이 발동하지 않아야 함)
- **현재:** `bars_held == 1`로 실패해야 정상 (RED 입증)

### GREEN

엔진 한 곳만 수정 — 타깃 청산은 `bb_middle`이 유효한 가격일 때만:

```python
hit_target = bb_middle > 0 and close >= bb_middle
should_exit = bars_held >= self.max_holding_bars or hit_target or hit_sl
```

- v1은 영향 없음 (`bb_middle`은 항상 양수 가격)
- v3/v4/v5는 `max_holding_bars`(기본 24봉) 시간 청산 또는 stop_loss로만 청산
- 기존 테스트 `test_c_buy_early_exit_at_bb_middle` 등은 그대로 통과해야 함

### REFACTOR / 문서 동기화

- `engine.py` 모듈 docstring §6.1 줄 보강: "BB 중심선 도달(`bb_middle > 0`인 시그널에 한함)"
- `DESIGN.md` §6.1 청산 규칙에 같은 단서 한 줄 추가 (§8이 아니므로 수정 가능)

### 범위 제한 (하지 말 것)

- **전략별 고유 청산 로직** (Donchian `exit_period` 채널 청산, RSI-2 청산 규칙 등) — Strategy Protocol
  확장이 필요한 설계 결정이므로 **별도 ADR + 별도 세션**. 이번 수정 후의 비교는
  "동일 시간 청산(24봉) 조건 하 **진입 신호 품질** 비교"로 의미가 한정됨을 인지할 것.
- v2(4지표)의 발화율 0 문제 조사 — 별도 트랙
- 엔진의 다른 파라미터/구조 리팩터링 금지 (surgical change)

---

## Task 2 — 비교 매트릭스 재실행 및 무결성 확인

1. 실행 (캔들 parquet은 이미 있음, fetch는 자동 skip):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\strategy_matrix.ps1
   ```

2. **무결성 체크:** 새 `reports/compare/strategy_matrix.csv`에서
   - v3/v4/v5의 `avg_bars_held`가 더 이상 일률적 1.0이 아닐 것 (1.0 초과~24.0 분포)
   - v1 칸들은 수정 전과 동일할 것 (영향 없음 회귀 확인 — 이전 CSV는 `reports/compare/strategy_matrix_pre_fix.csv`로 백업해 두고 비교)
3. 결과 **해석은 하지 말 것** — 해석은 Cowork 설계 세션 몫 (plans/strategy-comparison-matrix.md §6).

---

## 선택 (시간 남으면, 별도 1줄 커밋)

- `src/signal_program/strategies/__init__.py` `get_strategy()` docstring의 `"v1" 또는 "v2"` →
  `"v1"~"v5"` (stale 주석)

---

## 완료 기준 (품질 게이트)

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] RED 입증 → GREEN (신규 테스트 + 기존 엔진 테스트 전부 통과)
- [ ] 매트릭스 재실행, v3/v4/v5 `avg_bars_held` 정상화 + v1 회귀 없음 확인
- [ ] `CHANGELOG.md` Unreleased에 버그 수정 항목 추가
- [ ] 커밋 분리: ① 엔진 가드 + 테스트 + 문서, ② 매트릭스 재실행 산출물 (선택 docstring 수정은 ③)

---

## 세션 시작 명령

```powershell
cd C:\Users\user3\Desktop\VibeCoding\signal-up
claude "docs/prompts/backtest-engine-exit-guard-prompt.md 를 읽고 그대로 수행해줘"
```
