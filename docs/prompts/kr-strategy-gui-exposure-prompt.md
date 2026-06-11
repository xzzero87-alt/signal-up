# Claude Code 지시문 — 국장 전략(kr_strategy) GUI 노출 + 코인/국장 전략 표기 정합화

> **작성:** 2026-06-10 Cowork 세션 (FUNCTIONAL_TEST_REPORT_2026-06-10.md FINDING-3)
> **선행 숙지:** ADR-0018, CLAUDE.md 변경 금지 영역. **cli.py 러너 로직은 이번 범위에서 변경 금지.**

---

## 컨텍스트

사용자 발견 모순: 설정에서 전략 V1을 선택해도 대시보드 국장은 항상 "프랙탈". 원인은 표시 버그가 아니라:

1. `config.py:143` `kr_strategy: Literal["bb_cci", "fractal"] = "fractal"` (ADR-0018)이 **GUI/API에 미노출** — `SettingsUpdate`/`SettingsView`에 없음
2. 설정 페이지 전략 섹션(V1~V5)이 **코인 전용**이라는 표기 없음
3. **라벨 부정확**: `cli.py:400~409`에서 `kr_strategy != "fractal"`이면 국장 러너에 **코인 선택 전략 객체를 그대로 주입** (코인이 V4면 국장도 Donchian). 그런데 `dashboard.js:283` `KR_STRATEGY_LABEL = { fractal: '프랙탈', bb_cci: 'BB+CCI' }`는 항상 "BB+CCI"로 표시 → 부정확

## Task 1 — backend: kr_strategy를 SettingsUpdate/View에 노출

**TDD 등급: ★★★ (RED→GREEN)**

1. **RED**: `tests/` 적절한 위치(기존 settings API 테스트 파일)에 추가:
   - `PUT /api/settings {"kr_strategy": "bb_cci"}` → 200, GET에서 반영
   - `PUT {"kr_strategy": "fractal"}` → 200 왕복
   - `PUT {"kr_strategy": "v1"}` → 422
   - 422 후 기존 값 불변
2. **GREEN**:
   - `web/schemas.py`: `SettingsView`에 `kr_strategy: Literal["bb_cci", "fractal"] = "fractal"`, `SettingsUpdate`에 `kr_strategy: Literal["bb_cci", "fractal"] | None = None` (KIS 섹션 근처, 주석 ADR-0018)
   - `web/api/settings.py::_to_view`에 매핑 추가
   - `web/help_text.py`에 `"kr_strategy"` 도움말 추가: "국장 시그널 전략. 프랙탈=국장 전용(ADR-0018), 코인 전략 공유=위에서 선택한 코인 전략을 국장에도 적용."

## Task 2 — frontend: 설정 페이지 국장 전략 선택 UI + 코인 전용 라벨

**TDD 등급: ★★ (기존 form consistency 가드가 자동 검증)**

`src/signal_program/web/templates/settings.html`:

1. 전략 섹션 제목/안내를 **코인 전용임이 드러나게** 수정. 예: "2 전략" → "2 코인 전략", 안내 문구 "하나만 운용됩니다 — ..." 앞에 "코인에 적용됩니다." 명시
2. 전략 섹션 하단(V3~V5 패널 뒤)에 **국장 전략 서브섹션** 추가:
   - 제목: "국장 전략" + 도움말 `?` 버튼 (`data-help="{{ help['kr_strategy'] }}"`)
   - radio 2개 (`name="kr_strategy"`): `fractal` "프랙탈 (국장 전용, ADR-0018)" / `bb_cci` "코인 전략 공유"
   - 기존 strat-card 스타일 재사용 가능하면 재사용, 아니면 단순 radio + label (과한 신규 CSS 금지)
   - `err-kr_strategy` 스팬 포함
3. `dashboard.js:283`: `KR_STRATEGY_LABEL = { fractal: '프랙탈', bb_cci: '코인 전략 공유' }`로 라벨 정합화 (실동작 기준)
4. `settings.js`: 수정 불필요 확인 — radio string은 default 분기로 전송됨. `test_js_type_sets_match_schema`는 Literal을 제외하므로 통과해야 정상

**검증**: `tests/integration/test_settings_form_consistency.py` 통과 (새 input name이 SettingsUpdate에 있으므로). 추가로 같은 파일에:
- `/settings` HTML에 `name="kr_strategy"` radio 2개 존재 + 저장된 값에 checked
- 교차 일관성: `PUT kr_strategy=bb_cci` 후 `/api/dashboard` `settings_summary.kr_strategy == "bb_cci"`

## Task 3 (보너스 1줄) — FINDING-1: system.html dry_run err-span

`src/signal_program/web/templates/system.html`의 `dry_run` 체크박스 옆에 `<span class="field-error" id="err-dry_run"></span>` 추가 (같은 페이지 다른 필드와 동일 패턴).

## 완료 기준

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] 커밋 분리: Task 1(backend+test) / Task 2(frontend+라벨) / Task 3(한 줄)은 2~3개 커밋
- [ ] CHANGELOG.md Unreleased에 항목 추가
- [ ] 브라우저 수동 확인 1회: 국장 전략을 "코인 전략 공유"로 바꾸고 저장 → 대시보드 국장 뱃지가 "코인 전략 공유"로 표시

## 범위 제한 (하지 말 것)

- **cli.py 러너 로직 변경 금지** — bb_cci 분기의 실동작(코인 전략 주입)은 그대로 두고 라벨만 정합화
- `obv_lookback` 노출 금지 (보류 결정, V2 NO-GO)
- config.py `Settings` 시그니처 변경 금지 (필드 이미 존재)
- 전략 카드 UI 전면 개편 금지 — 서브섹션 추가만
