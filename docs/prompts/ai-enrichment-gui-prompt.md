# Claude Code 지시문 — AI enrichment 설정 GUI 노출 (ADR-0020, 세션 2/2)

> **작성:** 2026-06-10 Cowork. **선행:** 세션 1(`ai-enrichment-backend-prompt.md`) 머지 완료 후 시작.
> **교훈 반영:** FINDING-3 — GUI 미노출 설정은 화면 간 모순을 만든다. 백엔드와 같은 릴리스로 노출한다.

## Task 1 — 스키마/뷰 노출 (RED→GREEN)

**TDD 등급: ★★★** — kr_strategy 세션(`b037c25`)과 동일 패턴.

1. RED: 기존 settings API 테스트 파일에 추가 —
   - `PUT {"ai_enrichment_enabled": true}` → 200 + GET 반영
   - `PUT {"anthropic_api_key": "sk-ant-test1234"}` → 200, GET의 `anthropic_api_key_masked`가 `••••1234` 형태이고 원문 미노출
   - `PUT {"ai_enrichment_daily_cap": 0}` → 422 한국어 (`ge=1`)
   - `PUT {"ai_enrichment_timeout_seconds": 999}` → 422 (`le=120`)
2. GREEN:
   - `web/schemas.py` `SettingsView`: `ai_enrichment_enabled: bool = False`, `anthropic_api_key_masked: str = ""`, `ai_enrichment_model: str = "claude-haiku-4-5"`, `ai_enrichment_daily_cap: int = Field(default=30, ge=1, le=500)`, `ai_enrichment_timeout_seconds: int = Field(default=25, ge=5, le=120)`
   - `SettingsUpdate`: 같은 필드들 `| None = None` (api key는 `anthropic_api_key: str | None = None` — 쓰기 전용)
   - `web/api/settings.py::_to_view`: 매핑 + `mask_secret_value(s.anthropic_api_key)`
   - `web/help_text.py`: 5개 필드 도움말 (enabled에 "시그널 발송 후 AI가 최근 뉴스 요약을 후속 메시지로 첨부 (ADR-0020). 매수/매도 판단 아님" 취지 명시)

## Task 2 — 시스템 페이지 UI

**TDD 등급: ★★ (form consistency 가드 자동 검증)**

`web/templates/system.html` — 기존 "국장 연결 (KIS)" 섹션과 같은 구조로 "AI 컨텍스트 (Claude API)" 섹션 추가:

1. `ai_enrichment_enabled` 체크박스 (kr_enabled 패턴, err-span 포함 — FINDING-1 재발 금지)
2. `anthropic_api_key` `type="password"`, placeholder에 masked 값 (kis_app_key 패턴 그대로)
3. `ai_enrichment_model` 텍스트 입력, `ai_enrichment_daily_cap`·`ai_enrichment_timeout_seconds` 숫자 입력 (각각 err-span + 도움말 `?`)
4. `settings.js` 타입 집합 갱신: `STRING_FIELDS`에 `anthropic_api_key`·`ai_enrichment_model`, `INT_FIELDS`에 `ai_enrichment_daily_cap`·`ai_enrichment_timeout_seconds`, `CHECKBOX_FIELDS`에 `ai_enrichment_enabled` — `test_js_type_sets_match_schema`가 빠짐을 잡아줄 것

## Task 3 — 교차 일관성 (대시보드 표기)

**TDD 등급: ★★**

1. `web/api/dashboard.py` settings_summary에 `ai_enrichment_enabled` 추가
2. `dashboard.js` 운용 현황: enabled일 때 작은 뱃지 "AI 컨텍스트 ON" 표시 (코인 행 detail 끝에 텍스트 추가 수준 — 신규 CSS 최소화)
3. 테스트: `PUT ai_enrichment_enabled=true` → `/api/dashboard` summary 반영 (kr_strategy 교차 테스트 패턴)

## 완료 기준

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] 커밋 2개 권장: Task 1 / Task 2+3
- [ ] CHANGELOG.md Unreleased 항목
- [ ] 브라우저 수동 확인: 시스템 페이지에서 키 저장 → placeholder 마스킹 확인, 대시보드 뱃지 확인

## 범위 제한 (하지 말 것)

- 설정 페이지(settings.html) 변경 금지 — 이 기능은 시스템 페이지 소속 (텔레그램·KIS와 같은 "연결" 성격)
- enrichment 동작 로직 수정 금지 (세션 1 산출물)
- api key를 SettingsView에 평문 포함 금지 — masked 필드만
