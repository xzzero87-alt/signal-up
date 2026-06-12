# Claude Code 지시문 — v4 Donchian 워크포워드 (그리드 지원 확장 + 실행)

> **작성:** 2026-06-11 Cowork 설계 세션 (캡 결정 반영해 같은 날 개정)
> **선행 조건:** `strategy-owned-exit-prompt.md` 세션 완료 (ADR-0021 구현, a749f4d). 미완이면 중단하고 보고.
> **캡 결정 (2026-06-11):** 세션 1 재실행에서 v4 `avg_bars_held`가 24 캡에 몰림 — 채널 청산(exit_period=10)이
> 24시간 안에 거의 발동하지 않음. 태민 결정: **v4 평가는 캡 168봉(7일 안전망)으로 상향**.
> 단 기본값 24는 불변 (기존 매트릭스·v1 경로 영향 금지) — 캡은 CLI 옵션으로만 전달.
> **목적:** 매트릭스의 v4 우위가 기본 파라미터(20/10) 운빨인지 견고성 확인. 프레임 주의 —
> 이것은 **최적 파라미터 탐색이 아니라** "파라미터를 흔들어도 결과가 유지되는가" 확인이다.
> **선행 숙지:** `CLAUDE.md` 변경 금지 영역.

---

## 현재 상태 (Cowork에서 확인 완료)

walkforward는 v1/v2 전용이다:

- `backtest/walkforward.py:50` `StrategyParams` — V1/V2 필드만 (`extra="forbid"`)
- `walkforward.py:157` `_params_to_strategy` — v1/v2 분기만
- `walkforward.py:301` `parse_grid` — int 강제 변환이 `cci_threshold_normal` 하드코딩
- `cli.py:746` `_V1_DEFAULT_GRID` — v2만 기본 그리드 가드 존재

## Task 1 — StrategyParams v4 확장 (TDD ★★★)

- `StrategyParams`에 신규 필드: `donchian_entry_period: int | None = None`,
  `donchian_exit_period: int | None = None` (None = base_settings 기본값 유지 — V2 필드 패턴 동일)
- `parse_grid`의 int 변환: 하드코딩 if를 모듈 상수 `_INT_GRID_FIELDS = frozenset({"cci_threshold_normal", "donchian_entry_period", "donchian_exit_period"})`로 치환 (이 한 곳 외 로직 변경 금지)
- `_params_to_strategy`에 v4 분기: V2 패턴 재사용 — None 아닌 필드만 `base_settings.model_copy(update=...)` → `get_strategy("v4", effective)`
- 테스트: `tests/unit/backtest/test_walkforward.py`에 ① parse_grid가 donchian 필드를 int로 파싱,
  ② v4 _params_to_strategy가 오버라이드 반영된 DonchianStrategy 생성, ③ 기존 v1/v2 경로 회귀 없음

## Task 2 — CLI 가드 + 캡 옵션 배선

- `cli.py` walkforward: `strategy_version == "v4"`인데 그리드가 `_V1_DEFAULT_GRID` 그대로면
  v2 가드(746행 인근)와 같은 방식으로 명확한 에러 메시지 (조용한 V1 그리드 적용 금지)
- **캡 배선**: `backtest`·`walkforward` 두 명령에 `--max-hold` 옵션 추가 (기본 24 — 기본 동작 무변경).
  - backtest: `BacktestEngine(strategy=..., max_holding_bars=max_hold)` 전달
  - walkforward: `WalkforwardEngine`(또는 `_engine_factory`)에 전달돼 fold별 엔진 생성 시 적용
  - 테스트: `--max-hold 168`이 엔진까지 도달하는지 1건 (기존 기본값 경로 회귀 1건)

## Task 3 — 실행 및 기록 (코드 작업 아님)

### 3-0. 사전 점검 — 캡 168 성격 변화 확인 (walkforward 전에 반드시)

```powershell
uv run signal backtest --market KRW-BTC --from 2025-01-01 --to 2026-05-31 --strategy v4 --max-hold 168
uv run signal backtest --market KRW-ETH --from 2025-01-01 --to 2026-05-31 --strategy v4 --max-hold 168
uv run signal backtest --market KRW-XRP --from 2025-01-01 --to 2026-05-31 --strategy v4 --max-hold 168
```

`v4_summary.md` 서두에 캡 24(기존 매트릭스 FULL 행) vs 캡 168 비교 표 기록:
거래 수 / avg_bars_held / 누적 / MDD / 샤프. **avg_bars_held가 여전히 168 근처에 몰리면
채널 청산 미작동이 캡 문제가 아니라는 뜻 — 즉시 보고하고 walkforward 진행 여부 대기.**

### 3-1. walkforward 3마켓 (train 8m / validate 2m 기본값, 목적함수 기본 = validate Sharpe)

```powershell
uv run signal walkforward --market KRW-BTC --from 2025-01-01 --to 2026-05-31 --strategy v4 --max-hold 168 --grid "donchian_entry_period:10,20,30,55;donchian_exit_period:5,10,20" --report-html reports/walkforward/v4_KRW-BTC.html
uv run signal walkforward --market KRW-ETH --from 2025-01-01 --to 2026-05-31 --strategy v4 --max-hold 168 --grid "donchian_entry_period:10,20,30,55;donchian_exit_period:5,10,20" --report-html reports/walkforward/v4_KRW-ETH.html
uv run signal walkforward --market KRW-XRP --from 2025-01-01 --to 2026-05-31 --strategy v4 --max-hold 168 --grid "donchian_entry_period:10,20,30,55;donchian_exit_period:5,10,20" --report-html reports/walkforward/v4_KRW-XRP.html
```

(12조합 × fold 수 — 시간 걸리면 진행 로그만 남기고 대기)

**기록 항목** (콘솔 fold 테이블 → `reports/walkforward/v4_summary.md`에 표로):

- fold별 best_params / Train Sharpe / Val Sharpe / Val Cum.
- fold 간 best_params가 널뛰는지 (안정성), Train↔Val Sharpe 괴리 (과적합 신호)
- fold 테이블의 best_params가 `N/A`로 표시되는 칸이 있으면 **버그 보고** (과거 fold None 이슈
  재발 여부 확인 — 현행 코드엔 getattr N/A 폴백 있음, cli.py:803)

**해석 금지** — 수치 기록까지만. 판단은 Cowork 세션.

## 범위 제한 (하지 말 것)

- 목적함수 변경/추가, fold 구조 변경
- v3/v5 그리드 지원 (요청 없음)
- 그리드 값 임의 확장 (위 12조합 고정 — 탐색 공간을 늘릴수록 다중비교 함정)
- `max_holding_bars` **기본값(24) 변경 금지** — 캡 168은 v4 평가 실행에서 옵션으로만.
  캡을 그리드 차원에 넣는 것도 금지 (태민 결정: 36조합 다중비교 회피)

## 완료 기준 (품질 게이트)

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] Task 1 테스트 3건 + 기존 walkforward 테스트 전부 통과
- [ ] 3마켓 실행 완료 + `v4_summary.md` 기록
- [ ] `CHANGELOG.md` Unreleased 항목 추가
- [ ] 커밋 분리: ① 그리드 확장+테스트+CLI 가드, ② 실행 산출물·요약

## 세션 시작 명령

```powershell
cd C:\Users\user3\Desktop\VibeCoding\signal-up
claude "docs/prompts/walkforward-v4-prompt.md 를 읽고 그대로 수행해줘"
```
