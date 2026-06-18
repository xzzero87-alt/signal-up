# 국장 라이브 전환 구현 스펙 — 120분봉 fractal → 일봉 v1(평균회귀)

> 결정 근거: [ADR-0024](adr/0024-kr-daily-mean-reversion-redesign.md) (accepted).
> 확정 설계: **120분봉 완전 대체** + **장 마감 후 1회(일봉) 평가**.
> 진행: ADR-0019 Planner/Generator/Evaluator 루프. 각 단계 게이트 통과 후 다음 단계.

## 목표

국장 라이브 신호를 현행(120분봉 `KrFractalStrategy`)에서 **일봉 v1(`BbCciStrategy`) 평균회귀**로 전환한다. 라이브가 백테스트(ADR-0023/0024에서 검증한 것)와 동일 전략·타임프레임이 되도록 한다.

---

## Part 1 — 설정 (`src/signal_program/config.py`)

기존 필드 유지, 아래 추가/변경:

| 필드 | 변경 | 비고 |
|---|---|---|
| `kr_timeframe: Literal["intraday","daily"]` | **신규**, 기본 `"daily"` | 일봉 모드 활성. `"intraday"`면 기존 60/120분봉 동작 |
| `kr_strategy: Literal["bb_cci","fractal"]` | 기본값 `"fractal"` → **`"bb_cci"`** | 일봉 v1 채택(ADR-0024) |
| `kr_cooldown_hours_day: int` | **신규**, 기본 `20` | 종목당 하루 1신호 |

- `SettingsView`/`SettingsUpdate`(web/schemas.py)에도 3필드 노출 + `help_text.py` 도움말. JS 타입 집합(`settings.js`)도 갱신(기존 drift 가드 테스트 통과시킬 것).
- **주의**: 기본값 변경은 재시작 시 라이브 동작이 바뀜 — 의도된 전환이나 runbook에 명시.

## Part 2 — 전략 배선 (`src/signal_program/cli.py`, KR 조립부 ~411)

현재 `if kr_strategy=="fractal" → KrFractalStrategy / else → 코인 strategy 공유`를 아래로 교체:

```python
kr_strategy_obj: Strategy
if settings.kr_strategy == "bb_cci":
    from signal_program.strategies import _build_v1   # 또는 get_strategy("v1", settings)
    kr_strategy_obj = _build_v1(settings)              # KR 전용 v1, 코인과 독립
else:  # "fractal" — 하위호환(intraday 전용)
    from signal_program.strategies.kr_fractal import KrFractalStrategy
    kr_strategy_obj = KrFractalStrategy(
        fractal_lookback=settings.fractal_lookback,
        fractal_volume_threshold=settings.fractal_volume_threshold,
        fractal_volume_strong=settings.fractal_volume_strong,
    )
```

- `KrStockRunnerService(...)` 생성 시 **`cooldown_day=CooldownStore(path=Path("state/kr_cooldown_day.json"), cooldown=timedelta(hours=settings.kr_cooldown_hours_day))`** 추가 전달.
- `_build_v1`이 비공개면 `get_strategy("v1", settings)` 사용(동등).

## Part 3 — 러너 일봉 경로 (`src/signal_program/kr_runner.py`)

1. **`__init__`**: 파라미터 `cooldown_day: CooldownStore` 추가 → `self._cooldown_day`. 인스턴스 가드 `self._last_daily_date: date | None = None` 추가.
2. **`run_one_cycle`**: 쿨다운 선택 분기 확장 —
   ```python
   if timeframe == Timeframe.HOUR_1: cooldown = self._cooldown_60m
   elif timeframe == Timeframe.HOUR_2: cooldown = self._cooldown_120m
   else: cooldown = self._cooldown_day   # Timeframe.DAY
   ```
   `_process_symbol`의 `fetch_candles(..., timeframe=timeframe, count=200)`는 그대로 — 어댑터가 DAY 분기 처리(ADR-0023). 200 일봉이면 v1 BB/CCI 룩백 충분.
3. **`run_forever`**: 최상단에서 모드 분기.
   - `settings.kr_timeframe == "daily"`: 아래 일봉 스케줄.
   - 그 외: 기존 intraday 로직 유지.
   ```python
   # 일봉 스케줄 (매시 정각 깨어나되, 마감 후 1회만)
   while True:
       now = 다음 정각까지 sleep 후 datetime.now(_KST)
       if now.weekday() >= 5: continue                    # 주말 제외
       if now.hour < _DAILY_EVAL_HOUR: continue           # _DAILY_EVAL_HOUR = 16 (마감 15:30 후)
       if self._last_daily_date == now.date(): continue   # 당일 중복 방지
       cycle_id = uuid4().hex[:12]
       try:
           await asyncio.wait_for(self.run_one_cycle(now, cycle_id, Timeframe.DAY),
                                  timeout=float(self._settings.cycle_timeout_seconds))
           self._last_daily_date = now.date()
       except TimeoutError/Exception: 기존과 동일 로깅
   ```
   상수 `_DAILY_EVAL_HOUR = 16` 추가.

## Part 4 — 도메인 정합 (중요)

- **마감봉 포함**: 일봉은 **마감 후(16시) 평가**하므로 당일 일봉은 이미 마감 → 그 바를 평가해야 함. 기존 intraday 경로가 미마감 봉을 `iloc[:-1]`로 떨어내는 로직이 있다면, **DAY 경로에선 당일 마감봉을 떨어내지 말 것**(백테스트와 동일하게 마지막 마감 일봉 평가). `_process_symbol`에서 DAY 분기 확인.
- **시크릿 마스킹**: 기존 유지(변경 없음).
- **KST timezone-aware**: 기존 `_KST` 유지.

---

## 테스트 (각 Part 후)

- **config**: `kr_timeframe`/`kr_cooldown_hours_day` 기본값·파싱, `kr_strategy="bb_cci"` 라운드트립, JS 타입 drift 가드 통과.
- **cli/strategy**: `kr_strategy="bb_cci"` → `BbCciStrategy`(v1) 인스턴스 빌드 확인.
- **kr_runner (freezegun)**:
  - `run_one_cycle(DAY)` → `cooldown_day` 선택, `fetch_candles(timeframe=DAY)` 호출.
  - 일봉 스케줄: 평일 16시 1회 발화 / 같은 날 재발화 안 함(`_last_daily_date`) / 주말 스킵 / 장중(14시) 발화 안 함.
  - DAY 경로가 당일 마감봉을 평가(off-by-one 없음).

## 검증 게이트

1. `uv run ruff check src/ --fix && uv run ruff format src/`
2. `uv run mypy src/`
3. `uv run pytest --cov=src/ -m "" --cov-fail-under=70`
4. `uv run signal doctor`
5. **DRY_RUN E2E**: `.env`에 `DRY_RUN=true`, `kr_enabled=true`, `kr_strategy=bb_cci`, `kr_timeframe=daily` → 마감 후(또는 freezegun 16시) 국장 일봉 신호 1건 평가·마스킹·중복없음 확인.

## 문서 (마지막)

- **ADR-0018** Status → `superseded by ADR-0024`, 본문 상단에 supersede 주석(삭제 금지, 프로젝트 규칙).
- `docs/adr/README.md` 0018 행 상태 갱신.
- `CLAUDE.md` 핵심 명령/도메인 규칙에 국장=일봉 v1 반영, `docs/runbook.md` 국장 운영 절차(마감 후 1회) 갱신.

## 롤백

`kr_timeframe="intraday"` + `kr_strategy="fractal"`로 되돌리면 즉시 구 동작 복귀(코드 분기 보존). 데이터·쿨다운 파일은 분리되어 충돌 없음.
