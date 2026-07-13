# Claude Code 지시문 — M21: M2 월간 알림 AI 해설 (ADR-0033)

> **작성:** 2026-07-13 Cowork. **선행 숙지:** `docs/adr/0033-momentum-ai-commentary.md`,
> `docs/adr/0020-ai-signal-enrichment.md`, CLAUDE.md 변경 금지 영역.
> **원칙:** 알림 경로 무변경. 해설은 발송 성공 후 fire-and-forget. 모든 예외는 삼키고 로그만.
> **의존성 추가 없음. config 필드 추가 없음. GUI 변경 없음.**

## Task 1 — `AiEnrichmentService.enrich_momentum` (RED→GREEN)

**TDD 등급: ★★★** — `src/signal_program/enrichment.py`

모듈 상수 추가 (기존 `_SYSTEM_PROMPT`는 무변경):

```python
# 변경 금지 (ADR-0033 §3)
_MOMENTUM_SYSTEM_PROMPT = (
    "당신은 한국 주식시장 해설가입니다. 월간 모멘텀 리밸런스 결과를 받으면 "
    "(1) 신규 편입 종목 관련 최근 1개월 핵심 뉴스·테마를 한국어로 요약하고, "
    "(2) TOP10 구성의 쏠림(특정 업종·테마 집중)이 보이면 사실로만 지적하세요. "
    "각 사실 끝에 (출처도메인)을 표기하세요. 전체 6문장 이내. "
    "매수·매도 권유, 확률, 목표가, 시장 전망은 절대 언급하지 마세요. "
    "특이사항이 없으면 '특이사항 없음'이라고만 답하세요."
)
```

메서드 추가 (기존 `enrich`는 무변경, cap·마스킹·클라이언트 로직 공유):

```python
async def enrich_momentum(self, summary: str, month_label: str) -> None:
    """M2 리밸런스 해설 — ADR-0033. summary는 MomentumJob이 만든 사실 요약문."""
```

- `_reset_if_new_day()` → cap 초과 시 `log.info("enrichment_cap_reached", kind="momentum", ...)` 후 return.
- 성공 경로는 `_call_and_notify`와 동일 구조이되 별도 헬퍼 `_call_and_notify_momentum(summary, month_label)`:
  - payload: `system=_MOMENTUM_SYSTEM_PROMPT`, `max_tokens=700`,
    user content = `summary` 그대로, web_search `max_uses: 3`.
  - 발송 문구: `f"🤖 AI 월간 해설 — {month_label}\n{text}\n— 정보 제공 목적, 투자 판단 아님"`
  - `self._daily_count += 1`, `log.info("enrichment_ok", kind="momentum", ...)`.
- 모든 예외: `log.warning("enrichment_failed", kind="momentum", exc_type=..., api_key_hint=self._mask_key())` — **절대 raise 금지**.

공통화를 위해 `_call_and_notify`를 리팩터링해도 되나(payload 빌더 분리 등),
기존 코인 경로의 로그 키·발송 문구·프롬프트는 바이트 단위로 보존할 것.

**테스트** (`tests/test_enrichment.py`의 기존 mock 패턴 재사용):
1. happy path: mock client 200 → `notify_text` 1회, 문구에 `AI 월간 해설`·`투자 판단 아님`·month_label 포함, count +1.
2. client 예외 → raise 없음, `notify_text` 미호출, count 불변.
3. cap 도달 상태 → API 미호출.
4. payload 검증: system이 `_MOMENTUM_SYSTEM_PROMPT`, user content == summary.
5. 기존 코인 `enrich` 테스트 전부 무변경 통과 (회귀 가드).

## Task 2 — `MomentumJob` 주입 + 발화 (RED→GREEN)

**TDD 등급: ★★★** — `src/signal_program/momentum/job.py`

1. 생성자에 keyword-only 파라미터 추가: `enricher: AiEnrichmentService | None = None`
   (TYPE_CHECKING import). `self._enricher = enricher`. 기본 None → 기존 동작 100% 불변.
2. `run_once`의 `if not dry_run:` 블록에서 **`send_text`·`_save_portfolio`·기존 로그 이후**에:

```python
if self._enricher is not None:
    summary = self._format_enrichment_summary(top, added, removed, asof, name_map)
    task = asyncio.create_task(
        self._enricher.enrich_momentum(summary, asof.strftime("%Y-%m"))
    )
    task.add_done_callback(lambda t: t.exception())  # 미회수 예외 경고 억제
```

3. 신규 `_format_enrichment_summary(...) -> str` — LLM에 줄 사실 요약(알림 포맷과 별개):

```
2025-12 마감 M2 리밸런스.
TOP10: 한화에어로스페이스(012450) +182.3%, ...  (12-1 모멘텀 내림차순, 종목명(코드) +모멘텀)
신규 편입: A(코드), B(코드) / 편출: C(코드)
top10 모멘텀 중앙값 +85.2%, 최고 +182.3%.
```

   (모멘텀 수치는 `top` DataFrame에서 계산. 섹터 정보는 없음 — 넣지 말 것.)

**테스트** (`tests/test_momentum_job.py` 기존 픽스처 재사용, enricher는 AsyncMock):
1. enricher 주입 + 정상 발송 → `enrich_momentum` 1회, 인자 (summary, "YYYY-MM").
2. `dry_run=True` → 미호출.
3. enricher None → 미호출 + 기존 run_once 반환 dict 회귀 없음.
4. `send_text`가 raise → `enrich_momentum` 미호출 (발송 성공 후에만).
5. summary 포맷: top10 전 종목 포함, 편입/편출 반영, 권유성 단어 없음.

## Task 3 — 조립 배선

**TDD 등급: ★** — `src/signal_program/cli.py`

`MomentumJob(...)` 생성 3곳(현재 318·370·618행 부근) 중 **데몬 경로 2곳**(run 318, serve 618)에서:

```python
momentum_enricher = None
if settings.ai_enrichment_enabled and settings.anthropic_api_key:
    from signal_program.enrichment import AiEnrichmentService
    momentum_enricher = AiEnrichmentService(settings, notifier.send_text)
runners.append(MomentumJob(settings=settings, notifier=notifier, enricher=momentum_enricher))
```

- 코인 러너용 enricher 인스턴스가 같은 스코프에 이미 있으면 **재사용**(cap 공유가 의도 — ADR-0033 §4). 없으면 위처럼 생성.
- 370행(수동 1회 실행 명령)은 **주입하지 않는다** — dry_run/수동 실행 해설 미발송(ADR-0033 §5).
- 테스트: serve 조립 테스트가 있으면 enricher 주입 여부 1케이스 추가, 없으면 생략 가능(P2).

## Task 4 — 품질 게이트 + 문서

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- `docs/runbook.md`에 1줄: 해설 미수신 시 `enrichment_failed` 로그 확인, 알림 자체는 영향 없음.
- ADR-0033 상태는 오너가 accept 후 구현 착수.

## 완료 기준 (Evaluator 검증 항목)

- [ ] 기존 테스트 전부 통과 (코인 enrich 경로 회귀 0)
- [ ] enricher 미주입/None 시 MomentumJob 동작 바이트 단위 동일
- [ ] 해설 실패가 리밸런스 알림·상태 저장에 영향 주는 경로 부재 (코드 리뷰로 확인)
- [ ] dry_run·수동 실행 시 API 호출 없음
- [ ] 시크릿 마스킹: 신규 로그에 api_key 원문 노출 없음
- [ ] 변경 파일: enrichment.py, momentum/job.py, cli.py, tests 2~3개, runbook — 그 외 없음

**구현 후 "변경 요약"을 회신하면 Evaluator 검증을 수행한다.**
