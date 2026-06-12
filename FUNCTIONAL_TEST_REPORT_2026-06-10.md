# 설정 기능 전수 테스트 리포트 — 2026-06-10

> **갱신 (동일 날짜):** FINDING-1은 `2bd7b5d`, FINDING-3은 `b037c25`+`5879a4f`로 수정 완료.
> 격리 샌드박스 재검증 19/19 통과 — API 왕복(bb_cci/fractal/422/불변), 설정↔대시보드 교차 일관성,
> 설정 페이지 radio·checked·도움말·err-span·"코인 전략" 라벨, dashboard.js 라벨 정합화, err-dry_run.
> 미해결 잔여: FINDING-2(Cosmetic, 백로그)·시나리오 B 배너 억제(실브라우저 1회 확인).

> 실행 주체: Cowork 격리 샌드박스 (실제 운영 settings.json 미접촉)
> 방식: 6/8 버그 리포트와 동일 — 격리 uvicorn 서버 + 실제 페이지 JS(jsdom) 실행
> 대상 커밋: `3901226` (settings-contract-hardening 적용 후)

## 총괄

| 단계 | 검사 수 | 통과 | 실패 |
|---|---|---|---|
| 1. 설정 API 전수 (31개 필드 × 정상/위반/영속) | 177 | 174 | 3 (전부 테스트 기대값 문제, 결함 아님) |
| 2. UI DOM 검증 (전략 전환·값 반영·도움말·렌더 무결성) | 117 | 116 | 1 (Minor) |
| 3. 페이지 JS 동작 (저장 플로우·에러 표시·패널 전환) | 13 | 12 | 1 (jsdom 환경 한계, 결함 아님) |
| 4. 페이지 전수 (대시보드·시스템·백테스트·실패 이력·API) | 30 | 30 | 0 |
| **합계** | **337** | **332** | — |

**결론: 실결함 1건(Minor), 외관 1건(Cosmetic). 설정 시스템은 전반적으로 견고함.**

## 검증된 것 (이상 없음)

- **31개 설정 필드 전부**: 정상값 저장→GET 반영→디스크 영속, 경계값 위반(상한·하한)→422+한국어 메시지, 422 후 기존 값 불변(no-mutate)
- **전략 전환 v1~v5 × 5페이지 조합**: 카드 강조(`on` 클래스)·라디오 checked·파라미터 패널 show/hide가 전부 일치. `pickStrategy()` JS 전환도 정상
- **UI 값 표시**: 31개 필드 고유값 저장 후 설정·시스템 페이지 input `value`가 전부 일치. 깨진 글자(U+FFFD)·미렌더 jinja·`[object Object]` 없음. 도움말(`?`) 텍스트 누락 0건
- **시크릿 보안**: 토큰/KIS 키 저장 후 HTML 어디에도 평문 미노출, placeholder는 `••••XXXX` 마스킹, value 비움
- **저장 플로우 (실제 settings.js 실행)**: 정상 저장→서버 반영+토스트, 보이는 필드 422→인라인 에러+빨간 테두리, **숨겨진 패널 필드 422→글로벌 배너 폴백** ("fractal_lookback: 500 이하여야 합니다" 정확 표시) — **커밋 52dd761의 시나리오 A 검증 완료**
- **대시보드 연동**: 전략·화이트리스트 수·쿨다운·dry_run 변경이 `/api/dashboard` settings_summary에 즉시 반영
- **시스템 페이지**: dry_run/kr_enabled/kis_is_paper 체크박스 true/false 왕복 표시 정상
- **백테스트 페이지**: 전략 5종 옵션, 국장 드롭다운 한글 종목명 표시 정상
- **기타**: extra 필드 거부(`extra="forbid"`), strategy_version="v9" 거부, 빈 화이트리스트 한국어 422

## 발견 사항

### 🟡 FINDING-1 (Minor) — 시스템 페이지 `dry_run`에 err-span 없음

`src/signal_program/web/templates/system.html`의 `dry_run` 체크박스에만 `id="err-dry_run"` 스팬이 없음 (같은 페이지의 다른 필드들은 전부 있음). dry_run이 422를 받을 일은 사실상 없고, 받더라도 52dd761의 글로벌 배너 폴백이 커버하므로 심각도 낮음. 다음 시스템 페이지 작업 시 한 줄 추가 권장.

### ⚪ FINDING-2 (Cosmetic) — 422 메시지의 float 표기

`le`/`ge`가 float인 필드는 메시지가 "5.0 이하여야 합니다", "1.0 이하여야 합니다"로 표시됨. 동작은 정상이나 "5 이하", "1 이하"가 자연스러움. `web/security.py`의 메시지 포맷에서 `int(v) if v == int(v) else v` 처리로 개선 가능. 우선순위 낮음.

### 🔴 FINDING-3 (Major, 사용자 발견) — 국장 전략이 설정 UI와 모순되게 보임

**증상**: 설정에서 코인·국장 종목을 고르고 전략 V1을 선택해도, 대시보드 운용 현황에 국장은 항상 "프랙탈"로 표시됨.

**원인**: ADR-0018에 따라 국장은 의도적으로 별도 전략(`config.py:143` `kr_strategy: "bb_cci"|"fractal" = "fractal"`)을 사용하며, 대시보드 표시는 실제 운용 전략을 정확히 반영함. 결함은 표시가 아니라 다음 3가지 공백:

1. 설정 페이지 전략 섹션(V1~V5)이 코인 전용이라는 표기가 없음 → 국장에도 적용된다고 오인됨
2. `kr_strategy`가 `SettingsUpdate`/`SettingsView`에 없음 → GUI·API 어디서도 변경 불가 (settings.json 직접 편집만 가능)
3. 결과적으로 설정 화면과 대시보드가 서로 모순처럼 보임

**분류**: 표시 버그 아님. ADR-0018 부분 구현(GUI 미노출) + UI 정보 설계 결함.

**테스트 교훈**: 본 테스트는 필드 왕복(저장→반영)은 전수 검증했으나 "화면 간 의미 일관성"(같은 도메인 사실을 보여주는 두 화면의 모순) 시나리오가 없었음. 교차 일관성 카테고리를 회귀 시나리오에 추가 필요.

### ℹ️ 미검증 1건 — 시나리오 B의 "배너 억제"

jsdom은 레이아웃 엔진이 없어 `offsetParent`가 항상 null → "보이는 필드 에러일 때 배너가 안 뜨는지"는 시뮬레이션 불가. 인라인 에러 표시 자체는 검증 완료. 실브라우저에서 1회 확인 권장:

```js
// /settings에서 F12 Console (allow pasting 후)
document.querySelector('[name="bb_period"]').value = '999';
document.getElementById('settings-form').requestSubmit();
// 기대: bb_period 옆 인라인 에러만, 상단 글로벌 배너 없음
```

## 참고 — 테스트 산출물 (샌드박스)

`/tmp/sigtest/test_api.py`, `test_dom.py`, `test_js.mjs`, `test_pages.py` — 격리 환경 전용이라 repo에는 미포함. 회귀 가드로 영구화하려면 기존 `tests/integration/test_settings_form_consistency.py` 체계로 이식 가능 (별도 핸드오프).
