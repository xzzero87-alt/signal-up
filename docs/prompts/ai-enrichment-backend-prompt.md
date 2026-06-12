# Claude Code 지시문 — AI 시그널 enrichment 백엔드 (ADR-0020, 세션 1/2)

> **작성:** 2026-06-10 Cowork. **선행 숙지:** `docs/adr/0020-ai-signal-enrichment.md`, CLAUDE.md 변경 금지 영역.
> **세션 범위:** 백엔드만. GUI 노출은 세션 2 (`ai-enrichment-gui-prompt.md`).

## 아키텍처 (ADR-0020 §Decision 요약)

```
runner: send_signal 성공 → (enabled && !dry_run) → asyncio.create_task(enricher.enrich(signal))
enricher: 일일 cap 확인 → httpx POST api.anthropic.com/v1/messages (web_search tool, timeout 25s)
        → 성공 시 notify_text(요약문) → 텔레그램 후속 메시지
        → 모든 예외/타임아웃: log.warning 후 종료 (절대 raise 금지)
```

## Task 1 — config 필드 추가

**TDD 등급: ★ (기존 config 테스트 패턴 따라 1~2개 추가)**

`config.py` `Settings`에 (ADR-0020 §5, 기존 필드 시그니처 변경 금지):

```python
# AI 시그널 enrichment (ADR-0020)
ai_enrichment_enabled: bool = False
anthropic_api_key: str = ""          # 시크릿 — 마스킹 대상
ai_enrichment_model: str = "claude-haiku-4-5"
ai_enrichment_daily_cap: int = Field(default=30, ge=1, le=500)
ai_enrichment_timeout_seconds: int = Field(default=25, ge=5, le=120)
```

## Task 2 — EnrichmentService (RED→GREEN)

**TDD 등급: ★★★**

신규 `src/signal_program/enrichment.py` (또는 `notifiers/enrichment.py` — 작성자 판단, 단일 파일):

```python
class AiEnrichmentService:
    def __init__(self, settings: Settings, notify_text: Callable[[str], Awaitable[None]],
                 *, _client: httpx.AsyncClient | None = None) -> None: ...
    async def enrich(self, signal: Signal) -> None: ...
```

**요구사항:**
1. 일일 cap: KST 기준 날짜가 바뀌면 카운터 리셋. cap 도달 시 호출 없이 `log.info("enrichment_cap_reached")` 후 반환
2. API 호출: `POST https://api.anthropic.com/v1/messages`, 헤더 `x-api-key`, `anthropic-version: 2023-06-01`. body: model, `max_tokens=500`, system 프롬프트(아래), user 메시지에 signal의 market/direction/mode/strength/price, tools에 `{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}`
3. system 프롬프트 (상수, 변경 금지 항목): 한국어 2~3문장, 최근 24시간 해당 자산 관련 핵심 뉴스/이벤트 요약, 각 사실 끝에 (출처도메인), **매수/매도 권유·확률·목표가 금지**, 뉴스 없으면 "특이 뉴스 없음"이라고만
4. 응답 파싱: content 블록 중 `type=="text"` 텍스트만 연결. 텔레그램 발송 문구:
   `🤖 AI 컨텍스트 — {market}\n{text}\n— 정보 제공 목적, 투자 판단 아님`
5. **격리 실패**: timeout(`settings.ai_enrichment_timeout_seconds`), HTTP 오류, 파싱 오류 전부 `log.warning("enrichment_failed", ...)` 후 조용히 반환. API 키는 로그에 절대 노출 금지 (마스킹: 끝 4자)
6. 토큰 사용량 로그: 응답 `usage`를 `log.info("enrichment_ok", input_tokens=..., output_tokens=...)`

**RED 테스트 먼저** (`tests/unit/test_enrichment.py`, httpx는 `_client` 주입 + `httpx.MockTransport` 사용 — 신규 의존성 금지):
- 정상 응답 → notify_text가 기대 포맷으로 호출됨
- API 500 → notify_text 미호출, 예외 전파 없음
- 타임아웃 → 동일
- cap 도달 → HTTP 호출 자체가 없음
- cap이 KST 자정 경과 후 리셋 (freezegun 사용 가능 — 이미 dev 의존성)
- 로그에 api key 원문 미포함

## Task 3 — 배선 (runner + TelegramNotifier + cli)

**TDD 등급: ★★ (통합 테스트 1개)**

1. `notifiers/telegram.py` `TelegramNotifier`에 공개 메서드 `async def send_text(self, text: str) -> None` 추가 — 기존 sendMessage 내부 로직 재사용. **`Notifier` Protocol(`notifiers/base.py`)은 수정 금지** (§8.4 hard line)
2. `runner.py` `RunnerService.__init__`에 keyword-only 옵션 추가: `on_signal_sent: Callable[[Signal], Awaitable[None]] | None = None` (기본 None — 기존 호출부 무변경). `send_signal` 성공 + `not dry_run` 직후:
   ```python
   if self._on_signal_sent is not None:
       asyncio.create_task(self._on_signal_sent(signal))
   ```
3. `cli.py` serve/run 조립부: `settings.ai_enrichment_enabled and settings.anthropic_api_key`일 때만 `AiEnrichmentService` 생성, `notify_text=notifier.send_text`로 주입
4. 통합 테스트: runner가 시그널 발송 시 on_signal_sent가 호출되는지 / None이면 아무 일 없는지 / enrichment 콜백이 예외를 던져도 사이클이 죽지 않는지(create_task 격리)

## 완료 기준

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] 커밋 분리: Task 1+2(서비스+테스트) / Task 3(배선) 권장 2커밋
- [ ] CHANGELOG.md Unreleased 항목
- [ ] ADR-0020 Status를 `proposed` → `accepted`로 변경 (구현 머지 시점)
- [ ] 수동 스모크 (선택): 임시 키로 `ai_enrichment_enabled=true` 후 scan 1회 — 실키 없으면 생략

## 범위 제한 (하지 말 것)

- anthropic SDK 등 **신규 의존성 추가 금지** — httpx만 사용
- `Notifier` Protocol·DESIGN §8.1~8.5 시그니처 수정 금지
- 국장(kr_runner) 경로 연동 금지 — 코인 경로 검증 후 별도 세션
- GUI/스키마(SettingsUpdate/View) 노출 금지 — 세션 2 범위
- 시그널 발송 경로의 동기 흐름 변경 금지 (enrichment는 create_task로만)
