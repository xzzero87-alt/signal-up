# Claude Code 지시문 — 설정 폼 계약 강화 (Silent Fail 차단 + 타입 Drift 가드)

> **작성:** 2026-06-10 Cowork 세션 (코드 리뷰 기반)
> **배경:** BUG-1(2026-06-08)의 근본 원인 중 절반만 수정된 상태. 같은 사고 패턴 재발 방지가 목표.
> **선행 숙지:** `CLAUDE.md` 변경 금지 영역 — DESIGN.md §8.1~8.5 도메인 시그니처 불변, 자동매매 코드 금지.

---

## 컨텍스트 — 왜 이 작업인가

설정 필드 하나가 **5곳에 수동 동기화**되어 있다:

1. `src/signal_program/config.py` — `Settings`
2. `src/signal_program/web/schemas.py` — `SettingsView`
3. `src/signal_program/web/schemas.py` — `SettingsUpdate` (`extra="forbid"`)
4. `templates/settings.html` — 폼 input
5. `src/signal_program/web/static/js/settings.js` — `INT_FIELDS`/`FLOAT_FIELDS`/`STRING_FIELDS`/`CHECKBOX_FIELDS`

이 중 **필드 존재 여부**는 `tests/integration/test_settings_form_consistency.py`가 이미 가드한다 (BUG-1 수정 시 추가됨).
아직 무방비인 것 2가지:

- **(A)** 숨겨진 전략 패널의 필드에 422 에러가 매칭되면 **여전히 화면 무반응** (silent fail)
- **(B)** JS 타입 집합과 스키마 타입의 불일치 (예: int 필드가 `INT_FIELDS`에 빠지면 문자열로 전송됨)

---

## Task 1 — 숨겨진 필드 에러 silent fail 차단

**TDD 등급: ★★ (접근 차용 — JS 테스트 인프라가 없으므로 수동 검증 절차로 대체)**

### 현재 동작 (결함)

`src/signal_program/web/static/js/settings.js`의 `showFieldErrors()` (line ~172):

```js
const el = document.getElementById('err-' + fieldName);
if (el) { el.textContent = message; matchedCount++; }
...
if (matchedCount === 0 && errors.length > 0) { showGlobalError(...) }
```

`matchedCount`가 **숨겨진 패널 내부의 에러 스팬에 매칭돼도 증가**한다.
시나리오: 사용자가 V1 패널만 보는 상태에서 숨겨진 V3 필드(`fractal_lookback` 등)가 422를 받으면 → 에러가 보이지 않는 스팬에 꽂힘 → `matchedCount >= 1` → 글로벌 배너 폴백 안 됨 → **사용자에겐 저장 성공처럼 보임**. (BUG-1 보고서의 "보강" 항목이 미구현된 상태)

### 수정안

`showFieldErrors()`에서 매칭 카운트를 **"사용자에게 보이는 매칭"만** 세도록 변경:

```js
const el = document.getElementById('err-' + fieldName);
if (el) {
  el.textContent = message;
  // display:none 조상이 있으면 offsetParent === null → 보이지 않는 매칭
  if (el.offsetParent !== null) matchedCount++;
}
```

- 스팬에 메시지를 쓰는 동작과 input 빨간 테두리는 **유지** (패널 전환 시 보이도록)
- 보이는 매칭이 0건이면 기존 글로벌 배너 폴백 로직이 그대로 동작 → 변경은 이 한 곳뿐
- 기존 `matchedCount === 0` 조건문, `showGlobalError` 요약 포맷은 **수정 금지** (surgical change)

### 검증 (수동, 브라우저)

1. `uv run signal serve` → `/settings` 접속, 전략 V1 선택 상태 확인
2. DevTools Console에서 숨겨진 필드에 범위 밖 값 주입 후 저장:
   ```js
   document.querySelector('[name="fractal_lookback"]').value = '9999'; // ge=2, le=500 위반
   document.getElementById('settings-form').requestSubmit();
   ```
3. **기대:** 글로벌 에러 배너(`#form-errors`)에 `fractal_lookback: ...` 요약 표시
4. **회귀 확인:** 보이는 필드(예: `cooldown_hours=999`) 에러 시 기존처럼 인라인 스팬에만 표시되고 글로벌 배너는 안 뜸

---

## Task 2 — JS 타입 집합 ↔ 스키마 타입 일치 회귀 가드

**TDD 등급: ★★★ (테스트가 산출물 — RED는 mutation으로 입증)**

### 무엇을 가드하나

`SettingsUpdate`의 각 필드 타입과 `settings.js` 타입 집합의 **양방향 일치**:

| 스키마 타입 (`X | None`) | 기대 JS 집합 |
|---|---|
| `int` | `INT_FIELDS` |
| `float` | `FLOAT_FIELDS` |
| `str` | `STRING_FIELDS` |
| `bool` | `CHECKBOX_FIELDS` |
| `list[str]` | 제외 (hidden input mirror 별도 경로) |
| `Literal[...]` (`strategy_version`) | 제외 (radio/select) |

양방향 = ① 스키마의 모든 int/float/str/bool 필드가 해당 JS 집합에 존재, ② JS 집합의 모든 멤버가 `SettingsUpdate`에 존재 (오타·죽은 항목 차단).

### 구현

- **위치:** `tests/integration/test_settings_form_consistency.py`에 테스트 추가 (같은 가드 테마, 신규 파일 만들지 말 것)
- JS 파싱: `Path(signal_program.web.__file__).parent / "static" / "js" / "settings.js"`를 읽어 정규식으로 4개 `Set([...])` 리터럴에서 필드명 추출. 주석(`//`)이 배열 안에 섞여 있으니 `'([a-z0-9_]+)'` 패턴으로 따옴표 항목만 추출
- 스키마 타입 판별: `SettingsUpdate.model_fields[name].annotation`에서 `Optional` 벗기고 base type 매핑 (`typing.get_args` 사용)
- 실패 메시지에 **어느 방향의 어떤 필드가 빠졌는지** 명시 (기존 테스트의 한국어 메시지 스타일 유지)

### RED → GREEN 절차

1. **RED 입증 (mutation):** 테스트 작성 후, `settings.js`의 `INT_FIELDS`에서 `cooldown_hours`를 임시 제거 → 테스트 실패 확인 → **즉시 복원**. 커밋에는 mutation 포함 금지
2. **GREEN:** 원본 상태에서 테스트 통과 확인 (2026-06-10 리뷰 기준 현재 drift 없음 — 통과해야 정상. 만약 실패하면 실제 drift 발견이니 JS 집합을 스키마에 맞춰 보정하고 커밋 메시지에 명시)

---

## 완료 기준 (품질 게이트)

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] Task 1: 수동 검증 시나리오 2건 통과 (숨김 필드 → 배너 / 보이는 필드 → 인라인만)
- [ ] Task 2: mutation RED 입증 후 원본 GREEN
- [ ] `CHANGELOG.md`에 두 항목 추가 (Unreleased 섹션)
- [ ] 커밋 분리: Task 1과 Task 2는 별도 커밋 (각각 독립 revert 가능하게)

## 범위 제한 (하지 말 것)

- 설정 필드의 단일 정의 소스화(코드 생성) 같은 구조 개편 — 이번 범위 아님 (필요 시 별도 ADR로)
- JS 테스트 인프라(package.json, jsdom) 도입 — 이번 범위 아님
- `showFieldErrors` 외 settings.js 다른 함수 리팩터링 금지
