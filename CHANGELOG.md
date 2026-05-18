# Changelog

이 프로젝트의 모든 주목할 만한 변경 사항을 기록합니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르고,
이 프로젝트는 [Semantic Versioning](https://semver.org/lang/ko/)을 준수합니다.

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
