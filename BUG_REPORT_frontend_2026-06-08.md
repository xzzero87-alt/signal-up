# 프론트엔드 테스트 버그 리포트 — 2026-06-08

> ✅ **처리 결과 (동일 세션 수정 완료, 3.11 검증)** — mypy 0 이슈 / 관련 테스트 통과
> - BUG-2 설정 페이지 500 → `settings.html` HEAD 복원
> - BUG-1 모든 저장 422 → `fractal_lookback`을 `SettingsView`/`SettingsUpdate`/`_to_view`/`settings.js` INT_FIELDS에 추가
> - BUG-3 V3~5 패널 중복 표시 → V1 조건 `!= 'v2'`→`== 'v1'` 교정 + 초기 `updateV2Dim()` 동기화
> - BUG-4 `/api/logs` 404 → `web/api/logs.py` 신규 엔드포인트 + `create_app(logs_path=...)` 주입
> - 회귀 가드 추가: `tests/integration/test_settings_form_consistency.py`(폼↔스키마, 전략 패널), `tests/unit/web/test_logs_api.py`
> - 아래 본문은 발견 시점의 원본 기록(참고용).

설정 화면을 유저처럼 항목별로 바꿔가며(헤드리스 브라우저 + 실제 서버) 테스트한 결과입니다.

## 테스트 환경 (참고)
- 격리 샌드박스에서 `uvicorn signal_program.web.app:create_app` 기동, 별도 venv·임시 state·더미 `.env(DRY_RUN=true)`. 사용자 `.venv`/실제 설정/텔레그램은 미사용.
- 프론트엔드는 jsdom으로 실제 페이지 JS(`settings.js`, 인라인 스크립트)를 실행하며 입력 변경·저장 클릭·네트워크 응답·JS 예외를 관측.
- 샌드박스 Python이 3.10이라 3.11 전용 기능(`datetime.UTC`, `enum.StrEnum`)은 코드 미수정 shim으로 우회. 아래 버그는 모두 **템플릿/스키마/JS 레벨**이라 Python 버전과 무관.
- "배포본"= 현재 `HEAD` 커밋(`5186062`) 기준에서도 재현됨을 명시.

---

## 🔴 BUG-1 (Critical, 배포본) — UI에서 모든 설정 저장이 항상 실패하고, 사용자에겐 성공처럼 보임
**증상**: 설정 페이지에서 어떤 값을 바꿔 저장하든 `PUT /api/settings`가 **HTTP 422**로 거부됨. 그런데 토스트도 에러 배너도 뜨지 않아 **사용자는 저장된 줄 안다**. 실제로는 아무것도 저장되지 않음.

**근본 원인**:
- 템플릿 `settings.html:158`이 V3 파라미터로 `fractal_lookback` 입력을 렌더함 → 폼에 `name="fractal_lookback"`가 **항상 존재**(V3 섹션은 숨겨져 있어도 DOM·FormData엔 포함).
- 그러나 `web/schemas.py`의 `SettingsUpdate`/`SettingsView`에는 `fractal_lookback` 필드가 **없음**, 그리고 `model_config = ConfigDict(extra="forbid")`(schemas.py:73).
- 결과: 저장 시 `{"field":"fractal_lookback","message":"Extra inputs are not permitted"}` 로 422.
- `settings.js`의 `showFieldErrors`가 이 에러를 `#err-fractal_lookback` 스팬(숨겨진 V3 섹션 내부)에 꽂음 → `matchedCount>=1`이라 **글로벌 에러 배너로 폴백하지 않음** → 화면엔 아무 표시 없음.

**재현**: `/settings` → 쿨다운 등 아무 값이나 변경 → 저장 → 응답 422, 화면 무반응, 값 미반영.
**직접 확인**: `PUT /api/settings {"fractal_lookback":100}` → 422 / `{"cci_period":21}` → 200.

**수정안(택1)**:
- (권장) `fractal_lookback`을 `SettingsUpdate`·`SettingsView`·`settings.py::_to_view`에 추가(이미 `config.Settings`엔 `fractal_lookback: Field(ge=2,le=500,default=100)`로 존재하는 실제 V3 파라미터). 더해 `settings.js`의 `INT_FIELDS`에 `fractal_lookback` 추가(현재 문자열 "100"으로 전송됨).
- 또는 템플릿에서 `fractal_lookback` 입력 제거(V3에서 이 파라미터를 노출하지 않기로 한다면).
- 보강: `showFieldErrors`가 "보이는 필드에 매칭된 에러가 0건"일 때도 글로벌 배너로 폴백하도록(숨겨진 섹션 필드만 에러일 때 silent fail 방지).

---

## 🟠 BUG-2 (High, 워킹트리 한정) — `/settings` 페이지가 HTTP 500
**증상**: 설정 페이지 진입 시 500. `Jinja2 TemplateSyntaxError: Unexpected end of template ... looking for 'endblock'`.

**근본 원인**: 워킹트리의 `src/signal_program/web/templates/settings.html`이 **400줄에서 잘림**(JS 문자열 `const row = el.closest('.ind-par` 중간에서 끊김). 닫는 `</script>`·`</div>`·`{% endblock %}`·`{% block scripts %}`가 통째로 사라짐. `{% block content %}`가 미종료되어 템플릿 컴파일 실패.
- `git status`: 해당 파일만 ` M`(수정됨). `HEAD`는 463줄 정상, 워킹트리는 400줄. `git diff --stat` = 64줄 삭제.
- `.git/index.lock`(0바이트)가 남아 있음 → 편집/저장이 중간에 깨진 정황.

**수정**: `git checkout -- src/signal_program/web/templates/settings.html` 로 복원(또는 잘린 끝부분 복구). 남은 `.git/index.lock`은 다른 git 프로세스가 없으면 삭제.
> 참고: HEAD 정상본으로 교체해 구동했을 때 나머지 버그(특히 BUG-1)는 그대로 재현되므로, 복원만으로 저장 문제는 해결되지 않습니다.

---

## 🟡 BUG-3 (Medium, 배포본) — V3/V4/V5 선택 상태로 진입하면 V1 파라미터 패널이 같이 보이고 카드가 2개 강조됨
**증상**: 저장된 전략이 V3·V4·V5일 때 `/settings`를 열면 선택한 전략 파라미터 + **V1(BB+CCI) 파라미터가 동시에 표시**되고, 전략 카드도 **V1과 선택 전략 2개가 강조(`on`)**됨. CLAUDE.md의 "선택한 전략의 파라미터만 표시" 규칙과 어긋남.

**실측**(헤드리스 초기 렌더):
```
saved=v3 | panels v1:SHOWN v3:SHOWN | cards.on=[v1,v3]
saved=v4 | panels v1:SHOWN v4:SHOWN | cards.on=[v1,v4]
saved=v5 | panels v1:SHOWN v5:SHOWN | cards.on=[v1,v5]
saved=v1 / v2 는 정상
```

**근본 원인**:
- 템플릿이 V1 카드 `on`·라디오 `checked`·`#v1-params` 표시 조건을 `strategy_version != 'v2'`로 작성(`settings.html:20, 22, 63`) → V3/V4/V5에서도 참.
- 초기 로드 시 `pickStrategy()`/`updateV2Dim()`를 **호출하지 않음**(정의만 있고 onchange·저장후에만 실행). 서버 렌더 상태가 그대로 노출됨.

**수정안**: 위 3곳 조건을 `== 'v1'`로 변경. 그리고 페이지 로드 시 `updateV2Dim()`(=현재 체크된 라디오로 `pickStrategy`) 1회 호출 추가.

---

## 🟢 BUG-4 (Low, 배포본) — 시스템 페이지가 존재하지 않는 `/api/logs` 호출(404)
**증상**: `/system` 로드 시 `GET /api/logs?limit=100` → 404. 페이지는 "로그 API 없음 — /logs 파일을 직접 확인하세요"로 graceful 처리되어 크래시는 아님(`system.html:104,118`).
**수정안**: `/api/logs` 엔드포인트를 구현하거나, 미구현이면 해당 fetch/버튼을 제거해 불필요한 404를 없앰.

---

## 🟢 관찰 (버그 아님 / 설계 확인 필요)
- **V2 가중치 합**: 프론트는 합이 1.00이 아니면 색으로만 경고하고, 백엔드는 합과 무관하게 저장 허용(각 0~1 범위만 검증). "사용자가 결정, 시스템은 계산기" 프레임과 일치하므로 의도라면 OK. 강제하고 싶다면 저장 전 확인 모달 정도.
- **정상 확인됨(이상 없음)**: 텔레그램 토큰/시크릿은 입력칸이 빈 값으로 렌더되어 "안 건드리고 저장" 시 마스킹값으로 덮어쓰지 않음(라운드트립 안전). 범위 위반 값(예: `bb_period=1`, `squeeze_quantile=1`, `cooldown_hours=100`)은 해당(보이는) 필드에 한국어 에러가 정상 표시됨. 단, 이 에러 표시 경로도 BUG-1 때문에 실사용에선 저장 자체가 막힘.

---

## 권장 처리 순서
1. **BUG-2** 복원(`git checkout`) → 페이지가 떠야 나머지 검증 가능.
2. **BUG-1** 수정 → 저장 기능 자체 복구(가장 영향 큼).
3. **BUG-3**, **BUG-4** 정리.
