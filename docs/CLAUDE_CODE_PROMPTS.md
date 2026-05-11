# Claude Code 지시문 가이드

> 이 문서는 **Claude Code CLI**에서 사용할 마일스톤별 지시문 모음입니다.
> **워크플로우:** 설계·결정은 Cowork(Claude)에서 합의·문서화 → 구현은 Claude Code CLI에서 마일스톤 단위로 진행.
> **사용법:** 다음 마일스톤 시작 시점에 해당 섹션을 복사해서 Claude Code 프롬프트에 그대로 붙여넣으세요.

---

## 사용 흐름

```
[Cowork에서 결정·설계] → [Claude Code에서 마일스톤 N 인계 프롬프트 실행]
       ↑                              ↓
       └──── (막히거나 결정 변경 필요 시) ──┘
```

## 공통 규칙 (모든 지시문에 암묵적으로 포함)

- `DESIGN.md §8.1~8.5` 도메인 시그니처는 **변경 금지** (신규 필드 추가만 허용)
- `~/.claude/CLAUDE.md` (Clean Code 가이드) + `.claude/CLAUDE.md` (프로젝트 진입점) 준수
- 새 의존성 추가 시 PR 본문에 사유와 대안 검토 결과 명시
- 도메인 의미 있는 값은 config로 분리 (자명한 리터럴 제외)
- 하위 계층에서 `except Exception` 금지 (최상위 경계만 로깅과 함께 허용)
- 시크릿(텔레그램 토큰 등)은 응답·로그에서 마스킹
- 비-localhost 바인드 시 `WEB_AUTH_PASSWORD` 강제 가드 필수
- 모든 마일스톤은 `ruff check / ruff format / mypy --strict / pytest` 통과 필수

---

## 0. 첫 진입 (오리엔테이션)

`claude` 명령으로 처음 진입한 직후 **한 번만** 실행. 코드는 작성하지 않음.

```
이 저장소의 PRD.md, DESIGN.md, README.md, docs/adr/README.md, .claude/CLAUDE.md를
순서대로 읽고 다음을 한국어로 보고해줘:

1. 프로젝트 목적과 핵심 도메인 규칙 (한 줄 요약)
2. 변경 금지 영역(Hard Lines) 3가지
3. 16개 마일스톤 중 어디까지 진행됐고 다음은 무엇인지
4. 코드 시작 전 확인 필요한 환경 항목 (uv 설치, .env 등)
5. PRD §8.2 Outstanding 질문 중 다음 마일스톤에 영향을 줄 만한 것

코드는 아직 작성하지 마. 보고만.
```

---

## 마일스톤 1 — 프로젝트 스캐폴딩

```
DESIGN.md §14의 마일스톤 1을 구현해줘.

요구사항:
- pyproject.toml (Python 3.11, DESIGN.md §9.1 런타임 의존성 + §9.2 dev 의존성 그대로)
- .env.example (DESIGN.md §10의 모든 키, Q1 화이트리스트 20개 그대로)
- 디렉토리 구조 (DESIGN.md §7.2: src/signal_program/{indicators,strategies,exchanges,notifiers,backtest,charting,state,web}/, tests/{unit,integration}/)
- 각 패키지에 빈 __init__.py
- typer 기반 CLI 골격 (DESIGN.md §11)
  - signal doctor: 실제 동작 (업비트 API 핑 + 텔레그램 API 핑 + 화이트리스트 코인 검증)
  - run / serve / scan-once / backtest / fetch-candles: NotImplementedError stub
- structlog 기본 설정: KST 타임존, JSON 출력, 상관 키 contextvars
- src/signal_program/config.py: pydantic-settings.BaseSettings (DESIGN.md §10 키 매핑, WEB_BIND 가드 포함)
- src/signal_program/exceptions.py: AppError 계층 (DESIGN.md §8.2 에러 정책)

산출물:
1. 변경/생성 파일 목록과 이유
2. 코드 (모든 새 파일 전체 내용)
3. uv sync && uv run signal doctor 실행 결과 캡처
4. ruff check / ruff format --check / mypy --strict / pytest --collect-only 모두 통과 출력
5. 다음 마일스톤(2 — 도메인 모델 + 지표) 진입 전 확인 사항

금지:
- DESIGN.md §8 도메인 모델 본격 작성 (마일스톤 2)
- 업비트 외 거래소 추상화 (Exchange Protocol 자체는 마일스톤 3에서 정의)
- 웹 백엔드 (마일스톤 13)
- 자동매매 관련 코드 (영구 금지, ADR-0002)
```

---

## 마일스톤 2 — 도메인 모델 + 지표

```
마일스톤 1 완료 상태에서 마일스톤 2를 구현해줘.

요구사항:
- src/signal_program/enums.py
  - DESIGN.md §8.1 그대로 (Timeframe, StrategyMode, SignalDirection, SignalStrength)
- src/signal_program/models.py
  - DESIGN.md §8.2 그대로 (Candle, IndicatorSnapshot, Signal)
  - Pydantic v2 ConfigDict(frozen=True, extra="forbid")
  - 시그니처 변경 금지 (필드 추가는 ADR 없이 금지)
- src/signal_program/indicators/bollinger.py
  - 순수 함수 — `def bollinger(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.DataFrame`
  - 외부 import 최소화 (pandas, numpy만)
- src/signal_program/indicators/cci.py
  - 순수 함수 — Typical Price 기반 표준 공식
- 단위 테스트:
  - tests/unit/test_bollinger.py
    - TradingView 등 알려진 레퍼런스 데이터 1~2 픽스처와 비교 (오차 ≤ 0.01%)
    - parametrize로 경계값(period=2, period=200, std_mult=0.5/3.0)
    - Hypothesis property 테스트: 양수 시계열에 대해 NaN/예외 없이 반환
  - tests/unit/test_cci.py — 동일 패턴

산출물:
1. 변경/생성 파일 목록
2. 코드 전체
3. uv run pytest tests/unit/ -v --cov=src/signal_program/indicators --cov=src/signal_program/models 결과
4. 인디케이터 두 모듈 + models.py 커버리지 100% 확인
5. 다음 마일스톤(3) 진입 사항

금지:
- 전략 코드 작성 (마일스톤 4~5)
- I/O (지표/모델은 순수)
- DESIGN.md §8.6 (Web API 스키마)는 마일스톤 13에서 다룸
```

---

## 마일스톤 3 — 업비트 클라이언트

```
마일스톤 2 완료 상태에서 업비트 REST 클라이언트를 구현해줘.

요구사항:
- src/signal_program/exchanges/base.py
  - Exchange Protocol — DESIGN.md §8.4 그대로
- src/signal_program/exchanges/upbit.py — UpbitClient 클래스
  - httpx.AsyncClient
  - DESIGN.md §4.1 엔드포인트 (markets, candles/minutes/60, candles/days)
  - asyncio.Semaphore(5)로 동시성 제한
  - tenacity로 5xx/429/네트워크 에러 재시도 (지수 백오프 1~10s, 최대 3회)
  - 응답의 candle_date_time_kst를 zoneinfo.ZoneInfo("Asia/Seoul") timezone-aware datetime으로 변환
  - Remaining-Req 헤더 파싱해 디버그 로그
- 통합 테스트:
  - tests/integration/test_upbit_client.py
  - pytest-vcr 카세트 (한 번 실제 API 호출 녹화 → 이후 카세트로 회귀)
  - 시나리오: list_krw_markets / fetch_candles 정상 / fetch_candles 빈 결과 / 429 재시도

산출물:
1. 코드 + VCR 카세트 파일
2. uv run pytest tests/integration/test_upbit_client.py -v
3. 다음 마일스톤 진입 사항

금지:
- 업비트 인증 API 사용 (ADR-0002 — 자동매매 차단의 일환)
- 시그널 평가 로직 (마일스톤 4~5)
```

---

## 마일스톤 4 — 전략 모드 A (평균회귀)

```
마일스톤 3 완료 상태에서 모드 A를 구현해줘.

요구사항:
- src/signal_program/strategies/base.py — Strategy Protocol (DESIGN.md §8.3)
- src/signal_program/strategies/bb_cci.py
  - BbCciStrategy 클래스, name = "bb_cci"
  - DESIGN.md §3.2 모드 A BUY/SELL/Strength 조건 정확 구현
  - 직전 마감봉 1개의 데이터로만 판정
  - 거래량 비율(직전봉 / 최근 20봉 평균) 계산 포함
  - PRD R-P0-3 수용 기준 모두 만족
- 합성 캔들 데이터 단위 테스트:
  - tests/unit/test_strategy_bb_cci.py
  - parametrize로 BUY 양성/음성, SELL 양성/음성, Strong/Normal 경계값
  - Hypothesis: 합성 시계열에 대해 예외 없음

산출물:
1. 변경/생성 파일
2. 코드
3. 테스트 결과 + 커버리지
4. 다음 마일스톤(5) 진입 사항

금지:
- 모드 B 구현 (마일스톤 5)
- 쿨다운 (마일스톤 6)
- 텔레그램 송출 (마일스톤 7)
```

---

## 마일스톤 5 — 전략 모드 B (스퀴즈 돌파)

```
마일스톤 4의 bb_cci.py에 모드 B를 추가해줘.

요구사항:
- DESIGN.md §3.3 모드 B 정확 구현
  - 스퀴즈: bb_width가 최근 SQUEEZE_LOOKBACK봉 중 SQUEEZE_QUANTILE 이하
  - BUY/SELL 조건 + Strength 정의
- evaluate()는 모드 A·B 둘 다 평가해 0~2개의 Signal 반환
- 합성 데이터 테스트 추가:
  - 스퀴즈 후 상단 돌파 → BUY
  - 스퀴즈 후 하단 이탈 → SELL
  - 스퀴즈 아닌 상태에서 같은 가격 패턴 → 시그널 없음
  - A·B 동시 트리거 케이스 → 두 Signal 반환
- IndicatorSnapshot.bb_width_quantile 채우기

산출물:
1. 코드
2. 테스트 결과
3. 다음 마일스톤(6) 진입 사항

금지:
- 모드 A 시그니처/필드 변경
```

---

## 마일스톤 6 — 쿨다운 + 상태

```
마일스톤 5 완료 후 쿨다운을 구현해줘.

요구사항:
- src/signal_program/state/cooldown.py
  - 키: (market, mode, direction)
  - 값: 마지막 송출 datetime
  - 영속: state/cooldown.json (JSON, ADR-0008과 정합)
  - 메서드: is_cooled_down(key, now) -> bool, mark_sent(key, now)
- freezegun 단위 테스트:
  - 같은 키 2시간 미만 → 쿨다운 활성
  - 같은 키 2시간 정확/초과 → 통과
  - 다른 키는 영향 없음
  - 디스크 영속 라운드트립 (저장 → 재로드 → 동일 동작)
- 파일 권한 600 (Unix)

산출물:
1. 코드 + 테스트
2. 다음 마일스톤(7) 진입 사항
```

---

## 마일스톤 7 — 텔레그램 노티파이어 (텍스트만)

```
마일스톤 6 완료 후 텔레그램 텍스트 알림을 구현해줘.

요구사항:
- src/signal_program/notifiers/base.py — Notifier Protocol (DESIGN.md §8.4)
- src/signal_program/notifiers/telegram.py
  - httpx로 sendMessage 직접 호출 (python-telegram-bot 미사용)
  - DESIGN.md §5.3 메시지 포맷 정확히 (가격, BB %B, CCI, 거래량 비율, 시각 KST, 모드, 강도)
  - 3회 재시도 + 지수 백오프
  - 토큰을 로그에 절대 노출 금지 (마스킹 헬퍼 사용)
  - dry_run=True면 송출 없이 로그만
- 통합 테스트 (httpx MockTransport 사용):
  - 정상 전송
  - 401 (잘못된 토큰)
  - 네트워크 에러 → 재시도 후 최종 실패 로그
  - dry_run 분기

산출물:
1. 코드 + 테스트
2. 다음 마일스톤(8) 진입 사항

금지:
- 차트 이미지 첨부 (마일스톤 8)
```

---

## 마일스톤 8 — 차트 생성 + sendPhoto

```
마일스톤 7 완료 후 차트 첨부를 추가해줘.

요구사항:
- src/signal_program/charting/snapshot.py
  - matplotlib (Agg 백엔드)로 BB 3선 + CCI 서브플롯 + 캔들 80봉
  - 트리거 봉을 ▲(BUY) / ▼(SELL) 마커로 강조
  - 1280×720, dpi=100, PNG
  - state/charts/{market}_{ts}.png에 저장
- notifiers/telegram.py에 send_photo 추가
  - chart_path가 있으면 sendPhoto + caption, 없으면 sendMessage fallback
- 24시간 지난 차트 PNG 자동 정리 함수 (state/cleanup.py 또는 cooldown.py에 추가)

산출물:
1. 코드 + 시각 검증용 샘플 PNG (테스트 fixture)
2. 통합 테스트
3. 다음 마일스톤(9) 진입 사항
```

---

## 마일스톤 9 — 라이브 러너

```
마일스톤 8 완료 후 라이브 루프와 signal run CLI를 완성해줘.

요구사항:
- src/signal_program/runner.py
  - asyncio.TaskGroup으로 평가 루프 + 텔레그램 송출
  - apscheduler 또는 asyncio cron으로 KST 정각 +30s에 트리거
  - 사이클당 cycle_id (uuid) 발급, 모든 로그에 상관 키
  - 화이트리스트 N개 코인을 Semaphore(5)로 평가
  - 시그널 발생 → 쿨다운 검사 → 차트 생성 → 텔레그램 송출 → state/signals.jsonl 누적
  - 실패한 코인은 스킵 + 다음 사이클 재시도
- cli.py의 signal run 명령을 NotImplementedError에서 실제 동작으로
- E2E 수동 검증: 1시간 대기 → 봉 마감 → 시그널 또는 "변동 없음" 로그

산출물:
1. 코드
2. dry-run으로 1사이클 시뮬레이션 결과
3. 다음 마일스톤(10) 진입 사항

금지:
- 웹 서빙 (마일스톤 13)
```

---

## 마일스톤 10 — 백테스트 엔진

```
마일스톤 9 완료 후 백테스트를 구현해줘.

요구사항:
- src/signal_program/backtest/metrics.py — DESIGN.md §8.5 그대로 (TradeRecord, BacktestResult)
- src/signal_program/backtest/engine.py
  - 봉 단위 시뮬레이터 (이벤트 드리븐 X)
  - 시그널 봉 → 다음 봉 시가 진입 (PRD R-P0-7)
  - 청산: 24봉 보유 OR BB 중심선 도달
  - 단일 코인, 단일 방향, 1포지션
  - 수수료 0.05%×2 + 슬리피지 0.05%
- src/signal_program/cli.py의 backtest 명령 구현
- 캔들 캐시: data/candles/{market}/60/{yyyy-mm}.parquet
- fetch-candles CLI도 같이 구현
- 합성 시나리오 단위 테스트 (test_backtest_engine.py)

산출물:
1. 코드 + 테스트
2. KRW-BTC 1년치 백테스트 실행 출력 (모드 A)
3. 다음 마일스톤(11) 진입 사항
```

---

## 마일스톤 11 — 백테스트 리포트 (HTML)

```
마일스톤 10 완료 후 리포트를 추가해줘.

요구사항:
- src/signal_program/backtest/report.py
  - rich.Table 콘솔 요약
  - templates/backtest_report.html.j2 (Jinja2): 누적수익률 라인차트(Chart.js CDN), 거래 목록 테이블, MDD 강조
  - reports/backtest_{symbol}_{from}_{to}_{ts}.html 생성
- backtest CLI에 --report html 옵션 추가

산출물:
1. 코드
2. 샘플 HTML 리포트 1개
3. 다음 마일스톤(12) 진입 사항
```

---

## 마일스톤 12 — 워크포워드

```
마일스톤 11 완료 후 워크포워드를 구현해줘.

요구사항:
- src/signal_program/backtest/walkforward.py
  - 8개월 학습 / 2개월 검증 슬라이딩 4구간
  - 학습 구간: 임계값 그리드 서치 (CCI ±100/±150/±200 × 거래량 1.0/1.5)
  - 검증 구간: 학습에서 선정된 파라미터로 평가
  - 결과를 BacktestResult로 묶되 in-sample/out-of-sample 분리 표기
- backtest CLI에 --walkforward 옵션 추가
- HTML 리포트에 out-of-sample 섹션 별도

산출물:
1. 코드
2. 1년치 KRW-BTC 워크포워드 결과
3. 다음 마일스톤(13) 진입 사항 — v1 코어 완료
```

---

## 마일스톤 13 — 웹 백엔드 골격 (FastAPI)

```
v1 코어(마일스톤 1~12) 완료 상태에서 v2.0 GUI 백엔드 골격을 구현해줘.

요구사항:
- src/signal_program/web/app.py — FastAPI 인스턴스 + 라우터 마운트 + CORS(localhost만)
- src/signal_program/web/schemas.py — DESIGN.md §8.6 그대로
- src/signal_program/web/api/{settings,signals,backtest,daemon,dashboard}.py 라우트 스켈레톤
  - GET /api/settings → SettingsView (마스킹)
  - PUT /api/settings → SettingsView
  - POST /api/settings/validate → ValidationResult
  - GET /api/dashboard, /api/signals
  - POST /api/backtest/runs, GET /api/backtest/runs/{job_id}
  - POST/GET /api/daemon/{start,stop,status}
- src/signal_program/web/security.py — 시크릿 마스킹 + Basic Auth 가드 (WEB_AUTH_PASSWORD)
- src/signal_program/state/settings_store.py — state/settings.json R/W (ADR-0008)
- cli.py에 signal serve 명령 추가
  - asyncio.TaskGroup으로 uvicorn + run_signal_loop 동시 구동
  - WEB_BIND가 비-localhost인데 WEB_AUTH_PASSWORD 비어 있으면 SystemExit
- tests/integration/test_web_api.py — FastAPI TestClient로 모든 라우트 200/422 확인

산출물:
1. 코드 + 테스트
2. uv run signal serve 후 curl http://localhost:8765/api/dashboard 결과
3. 비-localhost 바인드 + 빈 비번으로 시작 시 거부 동작 확인
4. 다음 마일스톤(14) 진입 사항

금지:
- HTML 페이지 (마일스톤 14)
- 백테스트 잡 큐 (마일스톤 15)
- 데몬 start/stop 실제 동작 (마일스톤 16) — status만 우선
```

---

## 마일스톤 14 — 설정·시그널 대시보드 페이지

```
마일스톤 13 완료 후 GUI 2개 페이지를 구현해줘.

요구사항:
- src/signal_program/web/templates/{base.html, index.html, settings.html} (Jinja2)
- 정적 자산 (web/static/{style.css, app.js}) — Vanilla JS, 외부 CDN 최소
- index.html (시그널 대시보드)
  - 카드: 데몬 상태, 다음 평가 시각, 최근 1시간 시그널 수
  - 코인 표: 가격, BB %B, CCI, 거래량 비율, 마지막 시그널
  - 최근 50개 시그널 리스트
  - 30초 폴링으로 /api/dashboard 호출
- settings.html (설정)
  - 폼: 화이트리스트, 임계값, 텔레그램 토큰(마스킹), dry_run 토글
  - "저장" / "검증" 버튼
  - 토큰 입력 후 화면 전환 시 마스킹 표시
- web/api/settings.py 실제 R/W 동작 (state/settings.json)
- 테스트: TestClient로 R/W 라운드트립, 마스킹 검증

산출물:
1. 코드
2. 시각 검증 (스크린샷 또는 수동 확인 리포트)
3. 다음 마일스톤(15) 진입 사항
```

---

## 마일스톤 15 — 백테스트 페이지

```
마일스톤 14 완료 후 백테스트 페이지를 구현해줘.

요구사항:
- src/signal_program/web/templates/backtest.html
- src/signal_program/web/jobs.py — asyncio.Queue 기반 백그라운드 잡 큐
  - 동시 실행 1건 제한 (큐 길이 1)
  - 진행률 콜백 (처리 봉 / 전체)
  - 결과: BacktestJob (status: queued/running/done/failed)
- web/api/backtest.py 실제 동작
- 프런트엔드: 폼 → POST /api/backtest/runs → job_id → 1초 폴링 → 진행률 → 결과 차트(Chart.js)
- 결과 차트: 누적수익률 라인 + 거래 목록 테이블

산출물:
1. 코드 + 테스트
2. 단일 백테스트 실행 → 결과 페이지 표시 시각 검증
3. 다음 마일스톤(16) 진입 사항
```

---

## 마일스톤 16 — 데몬 제어 + 보안 기본선

```
마지막 마일스톤. 마일스톤 15 완료 후 데몬 제어와 보안 폴리시를 마무리해줘.

요구사항:
- web/api/daemon.py 실제 start/stop
  - Stop: 진행 중 사이클 완료 후 graceful shutdown
  - Start: 즉시 다음 봉 마감 대기
  - 상태는 GUI 카드에 실시간 반영 (폴링)
- index.html에 Start/Stop 토글 버튼
- 보안 폴리시 회귀 테스트 (test_web_api.py 보강):
  - WEB_BIND=0.0.0.0 + 빈 비번 → 시작 거부
  - WEB_BIND=0.0.0.0 + 비번 → Basic Auth 강제
  - 모든 응답에서 텔레그램 토큰 마스킹 검증
  - state/settings.json 권한 600 검증 (Unix)
- README.md의 보안 경고 섹션 + 트러블슈팅 보강
- v2 GUI 완성 — README 로드맵 갱신

산출물:
1. 코드 + 테스트
2. 보안 회귀 테스트 통과 결과
3. 1주일 무인 운영 검증 시나리오 제안
4. v2 런칭 전 잔여 작업 (Outstanding Q3~Q10) 점검표

축하: 마일스톤 16 완료 시 v2.0 GUI 런칭 가능 상태.
```

---

## 일반 패턴 지시문

### 새 ADR이 필요한 결정이 발생했을 때

```
구현 중 [상황 설명] 결정이 필요해 보여.
docs/adr/template.md를 복제해 docs/adr/0009-{kebab-title}.md 작성하고,
docs/adr/README.md 인덱스에 행 추가해줘.

본 PR에는 ADR만 머지하고, 결정 본문 적용은 다음 PR에서.
ADR이 accepted되어야 해당 결정에 따른 코드 변경을 진행할 수 있다.

작성 시 Context는 5문장 이내, Alternatives는 최소 2개, Consequences는 Positive/Negative/Risks 모두 채울 것.
```

### 새 의존성 추가가 필요한 경우

```
[기능명] 구현에 [라이브러리명]이 필요해.
다음 순서로 진행해줘:

1. 추가 사유 + 대안 검토 (예: 표준 라이브러리·기존 의존성으로 가능한지)
2. 기존 의존성과 중복되지 않는지 확인 (httpx, pydantic, pandas 등은 이미 있음)
3. pyproject.toml 갱신 + uv sync로 lockfile 갱신
4. 라이선스 호환성 확인 (가능하면 MIT/Apache 2.0)
5. PR 본문에 사유와 대안 결과 명시

거절: 기존 의존성으로 충분히 해결 가능하면 새 의존성 추가하지 마.
```

### 테스트가 갑자기 깨질 때

```
이전에 통과하던 테스트가 깨졌어.

1. git diff로 최근 변경 확인 — 무엇이 영향을 줬는지 좁히기
2. 단일 실패 테스트로 좁혀 디버그 출력 (pytest -k name -vv)
3. 원인 분류:
   - 의도된 변경에 따른 테스트 갱신이 누락 → 테스트 갱신 + PR 본문에 사유
   - 의도하지 않은 회귀 → 변경 되돌리거나 수정
4. 외부 환경(API 응답 변경, 시간대 등) 의존성이 있는지 점검
5. flaky 의심 시 재실행 횟수와 결과 보고
```

### 변경 금지 영역을 건드려야 할 것 같을 때

```
[변경하려던 것]이 DESIGN.md §8.1~8.5 시그니처 또는 자동매매 차단(ADR-0002)에 해당해.

여기서 멈추고 다음 보고만 해줘:
1. 무엇을 어떻게 변경하려 했는지
2. 왜 변경이 필요한지
3. 변경하지 않고 우회 가능한지

코드를 변경하지 마. 사용자가 Cowork에서 PRD/DESIGN/ADR를 갱신한 뒤 다시 인계할 거야.
```

### Git 커밋 메시지 작성

```
이번 변경을 Conventional Commits 형식으로 커밋해줘.
- type: feat / fix / refactor / docs / test / chore / perf / deps / ci 중 택1
- scope: 마일스톤 또는 모듈명 (예: indicators, web, backtest)
- description: 한 줄 요약 (한국어 가능)
- body: 변경 이유, 영향 범위 (필요 시)
- footer: ADR 참조, BREAKING CHANGE 표기 (해당 시)

예:
feat(indicators): BB·CCI 지표 계산 모듈 구현 (마일스톤 2)

- DESIGN.md §3 정확 구현, 외부 레퍼런스 오차 ≤ 0.01%
- pandas Series 입출력 순수 함수
- Hypothesis property 테스트 포함

Refs: ADR-0001
```

---

## Cowork로 돌아오는 트리거

다음 상황에서는 Claude Code 진행을 멈추고 Cowork(여기)로 돌아오세요:

| 상황 | 이유 |
|------|------|
| `DESIGN.md §8.1~8.5` 시그니처를 수정해야 한다고 판단될 때 | 도메인 계약 변경은 PRD/DESIGN/ADR 동기화 필요 |
| 새 거래소·알림 채널 등 구조적 추가 | `Exchange`/`Notifier` Protocol 변경은 ADR 신설 후 진행 |
| 백테스트 결과로 임계값 영구 변경 결정 | 운영 회고 — Cowork에서 결정 후 ADR-0001 재검토 |
| 보안 가드 정책 변경 (LAN 노출 등) | ADR-0005·0006 영향 — 별도 ADR 필요 |
| Outstanding Q3~Q10 결정 시점 도래 | PRD §8.2 결정은 Cowork에서 받기 |
| Why/Alternatives/Trade-off가 명확하지 않은 결정 | ADR 표준 포맷에 맞춰 받기 |
| 마일스톤이 30분 이상 막힘 | 설계 자체에 모호함이 있을 가능성 — Cowork에서 명확화 |

Cowork로 돌아왔을 때 보고할 것:
- 어떤 마일스톤 진행 중이었는지
- 어디서 멈췄는지 (코드 위치 또는 결정 포인트)
- 본인이 떠올린 옵션들 (있다면)

---

## 마일스톤 완료 체크리스트 (모든 마일스톤 공통)

각 마일스톤 완료 후 PR 머지 전 다음을 모두 확인:

- [ ] `uv run ruff check src/ tests/ --fix` 통과
- [ ] `uv run ruff format src/ tests/` 통과
- [ ] `uv run mypy src/` (strict) 통과
- [ ] `uv run pytest --cov=src/ --cov-fail-under=70` 통과
- [ ] `uv run pip-audit` 신규 취약점 없음
- [ ] `DESIGN.md §8.1~8.5` 시그니처 변경 없음
- [ ] 새 시크릿 노출 없음 (로그·응답 마스킹)
- [ ] PR 본문에 변경 이유, 새 의존성 사유, ADR 참조
- [ ] Conventional Commits 형식 커밋 메시지
- [ ] CHANGELOG에 한 줄 추가 (선택)

---

## 연관 문서

- [`PRD.md`](../PRD.md) — Product Requirements (v2.2)
- [`DESIGN.md`](../DESIGN.md) — 기술 명세서 (v2.0)
- [`README.md`](../README.md) — 자가설치 가이드
- [`docs/adr/`](adr/) — Architecture Decision Records
- [`.claude/CLAUDE.md`](../.claude/CLAUDE.md) — Claude Code 진입점 (이 가이드와 함께 자동 로드 권장)
- `~/.claude/CLAUDE.md` — Clean Code 가이드 (글로벌)
