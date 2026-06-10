# Changelog

이 프로젝트의 모든 주목할 만한 변경 사항을 기록합니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르고,
이 프로젝트는 [Semantic Versioning](https://semver.org/lang/ko/)을 준수합니다.

## [Unreleased]

### 수정
- **백테스트 엔진 v3/v4/v5 1봉 청산 버그 수정** — `bb_middle=0.0`(비-BB 전략)에서 `close >= 0.0`이 항상 참이 되어 모든 포지션이 1봉 만에 청산되던 결함 수정. `hit_target = bb_middle > 0 and close >= bb_middle` 가드 추가. DESIGN.md §6.1 단서 동기화
- **settings.js `showFieldErrors` silent fail 차단** — 숨겨진 전략 패널 내부 에러 스팬에 매칭되어 `matchedCount >= 1`이 되던 결함 수정. `offsetParent === null` 조상 체크로 보이지 않는 매칭은 카운트하지 않아 글로벌 배너 폴백이 올바르게 동작

### 추가
- **JS 타입 집합 ↔ SettingsUpdate 타입 drift 가드** — `tests/integration/test_settings_form_consistency.py::test_js_type_sets_match_schema` 신규 추가. `settings.js`의 `INT_FIELDS`/`FLOAT_FIELDS`/`STRING_FIELDS`/`CHECKBOX_FIELDS`와 `SettingsUpdate` 스키마 타입의 양방향 일치 회귀 가드
- **`kr_strategy` backend 노출 (ADR-0018)** — `SettingsUpdate`/`SettingsView`에 `Literal["bb_cci", "fractal"]` 필드 추가. PUT/GET API 라운드트립 + 유효성 검사 + 불변 보장 테스트 4건. `help_text.py` 도움말 등록
- **설정 페이지 국장 전략 UI + 코인 전용 표기** — 전략 섹션 제목을 "코인 전략"으로 명확화. 국장 전략 radio 서브섹션(fractal/bb_cci) 추가. `dashboard.js` `KR_STRATEGY_LABEL.bb_cci` "BB+CCI" → "코인 전략 공유" 정합화
- **system.html dry_run err-span 추가** — `dry_run` 체크박스 옆 `<span class="field-error" id="err-dry_run">` 누락 보완 (FINDING-1)

---

## [2.3.0] — 2026-06-09

### 추가
- **GET /api/signals/{signal_id}/explanation** — 시그널 ID로 해석 결과 반환. `SignalExplanation` (신뢰도·요약·근거 목록·주의사항) (P2 v2.3)
- **신뢰도 점수 산출** — `confidence.score_confidence()` 순수 함수: STRONG+15·거래량 비율·CCI 극값·BB 극값·피드백 거짓신호율 페널티 합산 (0~100 정수) (P2 v2.3)
- **전략별 시그널 해석** — `signal_explainer.explain()`: A(평균회귀)·B(스퀴즈)·C(가중점수)·D(프랙탈)·E(Donchian)·F(RSI2) 각각 임계값 기반 pass/warn/neutral 상태 생성 (P2 v2.3)
- **대시보드 해석 패널** — 시그널 행 클릭 시 `.sig-explain-panel` lazy-load: 신뢰도 배지(High/Mid/Low)·근거 행·주의사항 렌더링 (P2 v2.3)

### 수정
- **라이브 코인 캔들 정렬 누락** — 업비트 최신순 반환 캔들 미정렬로 `iloc[-1]`이 ~200h 전 봉을 읽는 버그 수정 (P0)
- **미마감 봉 전략 평가 포함** — 진행 중 봉이 `iloc[-1]`에 들어올 수 있어 `iloc[:-1]`로 마감봉만 전달 (P0)
- **국장 빈 화이트리스트 전 종목 스캔** — `kr_enabled` 상태에서 국장 0개 선택 시 전 종목 스캔 제거, 빈 화이트리스트 = no-op (P1)

---

## [2.2.0] — 2026-06-09

### 추가
- **GET /api/markets/coins** — 업비트 KRW 마켓 목록 동적 조회 (v2.2 M1)
- **GET /api/markets/kr** — 국장 큐레이션 유니버스 43종 (`KrStock` 코드·이름·시장·섹터) (v2.2 M1)
- **설정 ①종목설정 멀티셀렉트** — 코인/국장 탭·검색·전체/주요/해제·선택 칩 요약. 수기 콤마 입력 폐지. (v2.2 M3)
- **설정 ②시스템 페이지** — 운영(타임프레임·쿨다운)·국장연결·알림 설정 별도 분리. (v2.2 M4)

### 변경
- **빈 선택 정책** — 코인+국장 화이트리스트 둘 다 비어있으면 설정 저장·데몬 시작 거부 (v2.2 M2)
- **국장 빈 화이트리스트** — `kr_enabled`인 채 국장 0개 선택 시 전 종목 스캔(구 동작) 제거. 빈 화이트리스트 = no-op (코인 러너와 대칭).

### 수정
- **라이브 코인 캔들 정렬 누락** — 업비트 최신순 반환 캔들을 정렬하지 않아 `iloc[-1]`이 ~200h 전 봉을 읽고 BB/CCI가 역순 계산되는 버그. `candles_to_df()`에 `sort_values("opened_at")` 추가.
- **미마감 봉 전략 평가 포함** — 정렬 후 `iloc[-1]`이 진행 중 봉일 수 있어 도메인 규칙("봉 마감 기준") 위반. `iloc[:-1]`로 마감봉 199개만 전달.

### 기타
- 국장 유니버스 43종 교차검증 완료 (코드·종목명 일치, 상장폐지·코드변경 없음)
- 알테오젠(196170) KOSDAQ→KOSPI 이전(2026-06) 반영
- `pytest-timeout` + `slow` 마커로 워크포워드 격리, 기본 실행 속도 개선

---

## [2.0.2] — 2026-05-19

### 수정
- **설정 GUI 화이트리스트 저장 결함** — `SettingsUpdate.whitelist_markets`가 `tuple[str,...] | None`으로 선언되어
  JSON list가 tuple로 coerce → `Settings._parse_whitelist`가 tuple을 거부
  → `"Value error, 화이트리스트를 파싱할 수 없음: tuple"` 422 에러로 저장 불가
  - `config.py` `_parse_whitelist`: tuple 입력 정상 처리 + 빈 목록 한국어 메시지 거부
  - `schemas.py` `SettingsUpdate.whitelist_markets`: `list[str] | None`으로 수정
  - `security.py` `friendly_validation_errors`: `value_error` 케이스 추가 ("Value error, " 영어 prefix 제거)

---

## [2.0.1] — 2026-05-19

### 수정
- **runner의 업비트 API URL 결함** — `_run_live_coro` / `_run_async`에서 `httpx.AsyncClient`에
  `base_url` 없이 `UpbitClient`에 전달하여 매시 폴링 시 19/19 마켓 모두
  `"Request URL is missing 'http://' or 'https://' protocol"` 에러로 실패
  (`signal doctor`는 전체 URL 직접 호출로 정상, `signal run` / `--start-daemon` 경로만 영향)

---

## [2.0.0] — 2026-05-18

### 추가
- **로컬 웹 대시보드** (FastAPI + Vanilla JS, `localhost:8765`)
- **GUI 4 페이지**: 설정 / 시그널 대시보드 / 백테스트 / 데몬 제어
- **새 CLI**: `signal serve` (웹 + 데몬 동시 구동, task supervisor 패턴)
- **백테스트 HTML 리포트** — 단일 파일 자기완결 (외부 CDN 0개)
- **워크포워드 검증** + 그리드 서치 (8개월 학습 / 2개월 검증 슬라이딩)
- **잡 큐 매니저** (asyncio, worker 1개, 최대 5건, timeout 15분)
- **HTTP Basic Auth** — LAN 노출 시 보안 가드 (localhost 우회)
- **잡 결과 retention** — 50개 OR 30일 보존
- **시그널 이력 영속화** — `state/signal_history.jsonl` (rotate 1MB)
- **한국어 검증 메시지** — Pydantic ValidationError → friendly_validation_errors
- ADR 0001~0009
- 운영 플레이북 `docs/runbook.md`

### 변경 (Breaking)
- **설정 영속화**: `.env` 단독 → `state/settings.json` **단일 source of truth** (ADR-0008)
  - 부팅 시퀀스: settings.json 존재 → JSON 로드 / 미존재 → .env 시드 (메모리만)
- 시크릿 마스킹 정책 강화 (`SettingsView` ≠ `SettingsUpdate` 분리)
- Windows atomic write 우회 (ADR-0009): Windows는 직접 쓰기, Unix는 tmp + os.replace
- `assert_safe_bind` / `BasicAuthMiddleware`가 `settings.web_auth_password`를 `settings_store`에서 받음 (환경변수 직접 호출 제거, ADR-0008 정합)

### 의존성 추가
- `fastapi>=0.115,<1.0` — 웹 백엔드
- `uvicorn[standard]>=0.30,<1.0` — ASGI 서버
- `jinja2>=3.1,<4.0` — HTML 템플릿
- `pyarrow>=17,<22` — parquet 캔들 캐시

### 보안
- WEB_BIND 비-localhost + 비번 미설정 → 시작 거부 (SystemExit)
- BasicAuthMiddleware는 비-localhost 바인드 시만 활성. `127.0.0.1` 요청은 우회
- `secrets.compare_digest` timing-safe 비교
- `settings_store`가 `utf-8-sig`로 BOM 자동 제거 (Windows PowerShell 호환)

### Known Issues (v2.1 예정)
- JSDOM/Playwright E2E 자동화 (silent failure 사전 차단)
- backtest.js의 422 처리를 settings.js와 동일하게 (필드별 표시)
- 백테스트 기간 표시 1일 갭 (입력 04-30 → 표시 04-29, 봉 마감 기준)
- GUI saveSettings 캐시 결함 (PowerShell 우회로 검증 완료)
- Chat ID 평문 노출 (시크릿 분류 검토)
- `autocomplete="off"` 속성 보강
- 워크포워드 fold 알고리즘 (16개월 데이터에서 3 fold 생성 사유)
- `web_auth_password` GUI 편집 (현재 settings.json 직접 또는 .env 부트스트랩)

### Migration (v1 → v2)
기존 v1 사용자:
1. `.env` 파일 보관 (변경 불필요)
2. `git pull` + `uv sync`로 의존성 갱신
3. `uv run signal serve`로 GUI 첫 실행
4. → `.env`의 값이 `state/settings.json`으로 자동 부트스트랩됨
5. 이후 설정 변경은 GUI 또는 settings.json 직접 편집

자동매매 코드는 v1·v2 모두 없습니다 (ADR-0002).

---

## [1.0.0] — 2026-05-12

### 추가
- v1 코어 (M1~M9): CLI + 텔레그램 알림 + 백테스트 엔진
- 19종 KRW 마켓 화이트리스트 (LTC 폐지로 20→19)
- BB(20-2) + CCI(20) 시그널 (모드 A 평균회귀 / 모드 B 스퀴즈 돌파)
- 1시간봉 단일 타임프레임
- 쿨다운 2시간 (동일 코인·모드·방향)
- structlog 구조화 로그 + KST tz-aware
