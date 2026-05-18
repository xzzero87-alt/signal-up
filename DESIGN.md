# 업비트 시그널 프로그램 — 설계 명세서

> **버전:** v2.0
> **최종 갱신:** 2026-05-07
> **목적:** Claude Code 구현 인계용 스펙
> **v2.0 변경 요지:** 로컬 웹 대시보드(FastAPI) 추가, GUI 4페이지(설정·대시보드·백테스트·제어), `signal serve` 신설
> **기준 코딩 가이드:** `~/.claude/CLAUDE.md` (Clean Code 가이드 v2026-04-11)
> **Python:** 3.11 / **툴체인:** uv + Ruff + mypy(strict) + pytest

## 변경 이력

| 버전 | 날짜 | 변경 |
|------|------|------|
| v1.0 | 2026-05-07 | 초안 — CLI + 텔레그램 + 백테스팅 |
| v2.0 | 2026-05-07 | 웹 대시보드(FastAPI) 추가, `web/` 계층 신설, `signal serve`, REST API 스키마(§8.6), 마일스톤 13~16 추가. §8.1~8.5 도메인 시그니처 **불변** |

---

## 1. 프로젝트 개요

업비트 KRW 마켓의 1시간봉 캔들을 주기적으로 수집해 **볼린저 밴드(BB)** + **CCI** 두 지표로 매수/매도 시그널을 감지하고 **텔레그램 봇으로 알림**하는 도구다. 동일한 전략·데이터 파이프라인을 재사용해 **백테스팅** 과 **로컬 웹 대시보드 GUI** 도 함께 제공한다.

자동매매는 하지 않는다. v2.0부터 **GitHub 공개 + 자가설치 모델**(PRD ADR-006). 사용자는 자기 PC에서 자기 텔레그램 봇 토큰으로 운영한다.

---

## 2. 기능 범위

### In Scope
- 업비트 KRW 마켓 1시간봉 캔들 수집 (REST 폴링)
- 화이트리스트 10~20개 코인 스캔
- BB + CCI 지표 계산
- 모드 A(평균회귀) + 모드 B(스퀴즈 돌파)
- 거래량/쿨다운/봉마감 필터
- 텔레그램 알림 (텍스트 + 차트 PNG)
- 백테스트 엔진, 워크포워드, HTML 리포트
- structlog 구조화 로그 + 상관 키
- CLI: `run`, `backtest`, `scan-once`, `doctor`, `fetch-candles`
- **(v2.0) 로컬 웹 대시보드 (FastAPI)** — `signal serve` 명령으로 기동
- **(v2.0) REST API** — GUI 백엔드, 외부 자동화에서도 재사용 가능
- **(v2.0) 4개 GUI 페이지** — 설정 / 시그널 대시보드 / 백테스트 / 데몬 제어

### Out of Scope (명시적 제외)
- 자동매매, 주문 실행, 업비트 인증 API
- KRW 외 마켓
- 다종목 포트폴리오 시뮬레이션
- 사용자 인증, 멀티유저 (자가설치는 1대 1사용자)
- **(v2.0 수정) 외부 인터넷 SaaS 호스팅** — 회원가입·결제·중앙 DB·다중 봇 관리 등은 별도 v3 프로젝트
- **(v2.0 신설) 데스크탑 설치 패키지(.exe/.app)** — Tauri/PyInstaller는 GUI v1 안정화 후 검토
- 텔레그램 외 알림 채널
- 뉴스/소셜 시그널
- 호가창/체결 데이터

> YAGNI 원칙에 따라 인터페이스 추상화는 최소한(`Exchange`/`Notifier` Protocol)으로만 유지.

---

## 3. 전략 명세

### 3.1 지표 정의

| 지표 | 파라미터 | 산출 |
|------|----------|------|
| Bollinger Bands | period=20, std_mult=2.0 | `bb_upper`, `bb_middle`, `bb_lower`, `bb_width`, `bb_pct_b` |
| CCI | period=20 | `cci` (Typical Price 기반 표준 공식) |

봉 마감 가격(close) 기준. `pandas`+`numpy` 직접 구현. 단위 테스트에서 알려진 레퍼런스 값과 비교.

### 3.2 모드 A — 평균회귀

**BUY (모두 만족):** `close ≤ bb_lower` AND `cci ≤ -100` AND `volume_ratio ≥ 1.0`
**SELL (모두 만족):** `close ≥ bb_upper` AND `cci ≥ +100` AND `volume_ratio ≥ 1.0`
**Strong:** `cci` 절대값 ≥ 200

### 3.3 모드 B — 스퀴즈 돌파

**스퀴즈:** 직전 마감봉 `bb_width`가 최근 120봉 중 하위 20% 분위 이하
**BUY:** 스퀴즈 + `close > bb_upper` + `cci > +100` + `volume_ratio ≥ 1.5`
**SELL:** 스퀴즈 + `close < bb_lower` + `cci < -100` + `volume_ratio ≥ 1.5`
**Strong:** 거래량 비율 ≥ 2.5배 또는 `bb_width` 분위 ≤ 10%

### 3.4 공통 필터

| 필터 | 정책 |
|------|------|
| 봉 마감 확정 | 항상 `close` 기준. 미마감 봉 제외 |
| 쿨다운 | 동일 (코인, 모드, 방향) → 2시간 내 1회만 송출 |
| 모드 충돌 | A·B 동시 트리거 시 둘 다 별도 알림 |
| 데이터 부족 | 캔들 수가 max(BB, CCI) + 60봉 미만이면 스킵 |

### 3.5 비즈니스 규칙

- 시그널은 **추천**이며 자동매매 명령 아님 (메시지에 "참고용" 명시)
- BUY/SELL 양방향. 청산 시그널은 v1에서 별도 송출하지 않음
- 메시지에 BB 위치, CCI 값, 거래량 비율 모두 동봉

---

## 4. 데이터 / API 명세

### 4.1 업비트 REST API

| 용도 | 엔드포인트 | 인증 |
|------|-----------|------|
| KRW 마켓 목록 | `GET /v1/market/all?isDetails=false` | 불필요 |
| 1시간봉 캔들 | `GET /v1/candles/minutes/60?market=&count=&to=` | 불필요 |
| 일봉(검증용) | `GET /v1/candles/days?market=&count=` | 불필요 |

- Base URL: `https://api.upbit.com`
- Rate limit: 공개 API 기준 IP당 ~10 req/sec, ~600 req/min. 응답 헤더 `Remaining-Req` 모니터링
- 동시성: `asyncio.Semaphore(5)` 시작값
- 재시도: 5xx/429/네트워크 → 지수 백오프(1s, 2s, 4s, max 10s) 최대 3회

### 4.2 데이터 캐시 (백테스트)

- 포맷: `parquet` (월 단위 파티셔닝)
- 경로: `data/candles/{market}/{timeframe}/{yyyy-mm}.parquet`
- 라이브 모드는 메모리 내 직전 N봉만 유지

---

## 5. 시그널 송출 정책

### 5.1 평가 주기
1시간봉 마감 직후 평가. KST 정각 +30~+90초 폴링. `apscheduler` 또는 `asyncio` 자체 루프.

### 5.2 쿨다운
메모리 + 파일 영속(`state/cooldown.json` 또는 `sqlite3`). 키: `(market, mode, direction)`, 값: 마지막 송출 timestamp.

### 5.3 텔레그램 메시지

```
{emoji} [{direction}-{strength}] {market} (1h) — Mode {mode}
가격: {price:,} KRW ({pct_change:+.2f}%)
BB: 위치 {bb_pct_b:.2f}σ ({bb_state})
CCI(20): {cci:.0f}
거래량: 평균의 {vol_ratio:.1f}배
시각: {ts_kst} KST

📊 차트 첨부
ℹ️ 참고용 시그널 — 매매는 직접 판단
```

### 5.4 차트 이미지 (matplotlib)

- 직전 80봉 캔들 + BB 3선 + CCI 서브플롯
- 트리거 봉 ▲/▼ 마커
- 1280×720 PNG, dpi=100
- 경로: `state/charts/{market}_{ts}.png` (24h 자동 정리)

### 5.5 텔레그램 통신

- `httpx` 직접 호출 (의존성 최소화)
- `POST /bot{token}/sendPhoto` (multipart, photo + caption)
- 실패 시 `sendMessage` fallback
- 3회 재시도 + 지수 백오프

---

## 6. 백테스팅 명세

### 6.1 시뮬레이션 규칙
- 봉 단위 시뮬레이터. 직전봉 시그널 → 다음 봉 시가 진입
- 단일 종목, 단일 방향, 1회 1포지션
- 청산: 24봉 보유 또는 BB 중심선 도달 중 빠른 쪽

### 6.2 비용 모델
- 수수료 0.05% × 2 + 슬리피지 0.05% (라운드트립 ≈ 0.20%)

### 6.3 평가 지표
거래 횟수(A/B 분리), 승률, 평균 수익률, 누적 수익률, MDD, 샤프 연환산, 평균 보유봉 수.

### 6.4 워크포워드
8개월 학습 / 2개월 검증 슬라이딩 4구간. 검증 구간 결과만 "out-of-sample" 표기.

### 6.5 리포트
콘솔(`rich.Table`) + HTML(`templates/backtest_report.html.j2`). 출력 경로 `reports/backtest_*.html`.

---

## 7. 아키텍처

### 7.1 계층 (v2.0 갱신)

```
cli (typer)              web (FastAPI)
   \                          /
    \                        /
     runner (라이브 루프)  ←  REST API (상태 조회·제어)
            ↓
     backtest.engine (시뮬레이터)
            ↓
     strategies (BB+CCI A/B)
            ↓
     indicators (BB, CCI 순수 함수)
            ↓
     exchanges.upbit  ↔  notifiers.telegram  ↔  state, charting
```

- `web` 계층은 `cli`와 **동격**(둘 다 사용자 진입점), 같은 `runner`/`backtest.engine`을 호출
- `signal serve`는 `web` + `runner`를 같은 프로세스에서 `asyncio.TaskGroup`으로 동시 구동
- 순수 → 부수효과 방향 유지. `indicators`/`strategies`는 순수, I/O는 바깥 계층에만

### 7.2 디렉토리 구조 (v2.0 갱신)

```
시그널 프로그램/
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── README.md                # v2.0: 5분 설치 가이드, 텔레그램 봇 만들기, 보안 경고
├── PRD.md
├── DESIGN.md                # 이 문서
├── docs/
│   └── adr/                 # ADR-001 ~ ADR-007 (PRD에서 분리해 보관)
├── src/
│   └── signal_program/
│       ├── __init__.py
│       ├── config.py
│       ├── enums.py
│       ├── models.py
│       ├── exceptions.py
│       ├── indicators/
│       │   ├── bollinger.py
│       │   └── cci.py
│       ├── strategies/
│       │   ├── base.py
│       │   └── bb_cci.py
│       ├── exchanges/
│       │   ├── base.py
│       │   └── upbit.py
│       ├── notifiers/
│       │   ├── base.py
│       │   └── telegram.py
│       ├── backtest/
│       │   ├── engine.py
│       │   ├── metrics.py
│       │   ├── walkforward.py
│       │   └── report.py
│       ├── charting/
│       │   └── snapshot.py
│       ├── state/
│       │   ├── cooldown.py
│       │   └── settings_store.py    # v2.0: GUI 저장 설정 영속화
│       ├── runner.py
│       ├── cli.py
│       └── web/                     # v2.0: 웹 백엔드 신설
│           ├── __init__.py
│           ├── app.py               # FastAPI 인스턴스 + 라우터 마운트
│           ├── api/
│           │   ├── settings.py      # 설정 R/W
│           │   ├── signals.py       # 시그널 이력 조회
│           │   ├── backtest.py      # 백테스트 작업 큐 + 결과
│           │   ├── daemon.py        # start/stop/status
│           │   └── dashboard.py     # 통합 대시보드 데이터
│           ├── schemas.py           # 요청/응답 Pydantic (§8.6 참조)
│           ├── deps.py              # 의존성 주입
│           ├── security.py          # 시크릿 마스킹, 옵션 비번 가드
│           ├── jobs.py              # 백테스트 백그라운드 큐
│           ├── static/              # CSS, JS, favicon
│           └── templates/           # Jinja2
│               ├── base.html
│               ├── index.html       # 시그널 대시보드
│               ├── settings.html
│               ├── backtest.html
│               └── partials/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_bollinger.py
│   │   ├── test_cci.py
│   │   ├── test_strategy_bb_cci.py
│   │   ├── test_cooldown.py
│   │   └── test_settings_store.py     # v2.0
│   └── integration/
│       ├── test_upbit_client.py
│       ├── test_backtest_engine.py
│       └── test_web_api.py            # v2.0: FastAPI TestClient
├── data/                              # parquet 캔들 캐시 (gitignore)
├── state/                             # 쿨다운, 설정, 차트 (gitignore)
├── reports/                           # 백테스트 HTML (gitignore)
└── templates/
    └── backtest_report.html.j2
```

### 7.3 의존성 방향 (v2.0 갱신)

```
cli, web                                (진입 계층)
    ↓
runner, backtest.engine, jobs           (오케스트레이션)
    ↓
strategies → indicators                 (도메인 로직, 순수)
    ↓
exchanges, notifiers, state, charting   (부수효과)
    ↓
config, models, enums, exceptions       (공통)
```

- `web` → `runner`/`backtest.engine` 호출 가능, 역방향 import 금지
- `web/schemas.py`만 `models`를 import해 REST 응답으로 직렬화

---

## 8. 핵심 도메인 모델 (구현 계약)

> **§8.1~8.5는 v1.0과 동일하며 변경 금지.** Pydantic 모델·Protocol 시그니처는 그대로. v2.0은 §8.6만 추가.

### 8.1 Enum

```python
# src/signal_program/enums.py
from enum import StrEnum

class Timeframe(StrEnum):
    HOUR_1 = "60"

class StrategyMode(StrEnum):
    MEAN_REVERSION = "A"
    SQUEEZE_BREAKOUT = "B"

class SignalDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"

class SignalStrength(StrEnum):
    NORMAL = "normal"
    STRONG = "strong"
```

### 8.2 도메인 모델 (Pydantic, frozen)

```python
# src/signal_program/models.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class Candle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    market: str
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float

class IndicatorSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width: float
    bb_pct_b: float
    cci: float
    volume_ratio: float = Field(ge=0.0)
    bb_width_quantile: float | None = None

class Signal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    market: str
    timeframe: Timeframe
    mode: StrategyMode
    direction: SignalDirection
    strength: SignalStrength
    price: float
    triggered_at: datetime
    indicators: IndicatorSnapshot
```

### 8.3 Strategy Protocol

```python
# src/signal_program/strategies/base.py
from typing import Protocol
import pandas as pd

class Strategy(Protocol):
    name: str
    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]: ...
```

### 8.4 Exchange / Notifier Protocol

```python
# src/signal_program/exchanges/base.py
from typing import Protocol
from datetime import datetime

class Exchange(Protocol):
    async def list_krw_markets(self) -> list[str]: ...
    async def fetch_candles(
        self, market: str, timeframe: Timeframe, count: int, to: datetime | None = None,
    ) -> list[Candle]: ...
```

```python
# src/signal_program/notifiers/base.py
from pathlib import Path
from typing import Protocol

class Notifier(Protocol):
    async def send_signal(self, signal: Signal, chart_path: Path | None) -> None: ...
```

### 8.5 백테스트 결과

```python
# src/signal_program/backtest/metrics.py
class TradeRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    market: str
    mode: StrategyMode
    direction: SignalDirection
    entry_at: datetime
    entry_price: float
    exit_at: datetime
    exit_price: float
    bars_held: int
    pnl_pct: float

class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    period_from: datetime
    period_to: datetime
    trades: tuple[TradeRecord, ...]
    win_rate: float
    avg_pnl_pct: float
    cumulative_return_pct: float
    mdd_pct: float
    sharpe_annualized: float
    avg_bars_held: float
```

### 8.6 Web REST API 스키마 (v2.0 신설)

```python
# src/signal_program/web/schemas.py
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, SecretStr

class SettingsView(BaseModel):
    """GUI에 표시되는 설정. 시크릿은 마스킹된 형태로만 응답."""
    model_config = ConfigDict(extra="forbid")

    whitelist_markets: tuple[str, ...]
    bb_period: int = Field(ge=2, le=200)
    bb_std_mult: float = Field(gt=0, le=5)
    cci_period: int = Field(ge=2, le=200)
    cci_threshold_normal: int = Field(ge=50, le=500)
    cci_threshold_strong: int = Field(ge=50, le=1000)
    volume_ratio_min_a: float = Field(ge=0)
    volume_ratio_min_b: float = Field(ge=0)
    squeeze_lookback: int = Field(ge=20, le=500)
    squeeze_quantile: float = Field(gt=0, lt=1)
    cooldown_hours: int = Field(ge=0, le=72)
    telegram_bot_token_masked: str       # "••••••••XXXX"
    telegram_chat_id: str | None
    dry_run: bool

class SettingsUpdate(BaseModel):
    """저장 요청 — 시크릿은 평문으로 받되 응답에는 평문 노출 금지."""
    model_config = ConfigDict(extra="forbid")

    whitelist_markets: tuple[str, ...]
    bb_period: int = Field(ge=2, le=200)
    bb_std_mult: float = Field(gt=0, le=5)
    cci_period: int = Field(ge=2, le=200)
    cci_threshold_normal: int = Field(ge=50, le=500)
    cci_threshold_strong: int = Field(ge=50, le=1000)
    volume_ratio_min_a: float = Field(ge=0)
    volume_ratio_min_b: float = Field(ge=0)
    squeeze_lookback: int = Field(ge=20, le=500)
    squeeze_quantile: float = Field(gt=0, lt=1)
    cooldown_hours: int = Field(ge=0, le=72)
    telegram_bot_token: SecretStr | None = None   # 변경 시에만 전달
    telegram_chat_id: str | None
    dry_run: bool

class CoinStateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str
    last_price: float
    bb_pct_b: float
    cci: float
    volume_ratio: float
    last_signal_at: datetime | None
    last_signal_direction: SignalDirection | None

class DashboardView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daemon_status: str                  # "running" | "stopped" | "starting"
    next_evaluation_at: datetime | None
    coin_states: tuple[CoinStateView, ...]
    recent_signals: tuple[Signal, ...]  # 최근 50개

class BacktestRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str
    period_from: date
    period_to: date
    modes: tuple[StrategyMode, ...]
    overrides: dict[str, float | int] = Field(default_factory=dict)

class BacktestJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: str                          # "queued" | "running" | "done" | "failed"
    progress_pct: float = Field(ge=0, le=100)
    result: BacktestResult | None
    error: str | None

class DaemonStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    started_at: datetime | None
    last_cycle_at: datetime | None
    next_evaluation_at: datetime | None

class ValidationResult(BaseModel):
    """signal doctor 동등."""
    model_config = ConfigDict(extra="forbid")
    upbit_ok: bool
    telegram_ok: bool
    whitelist_unknown_markets: tuple[str, ...]
    issues: tuple[str, ...]
```

**라우트 요약:**

```
GET  /api/settings                → SettingsView
PUT  /api/settings                → SettingsView (저장 + 마스킹 응답)
POST /api/settings/validate       → ValidationResult
GET  /api/dashboard               → DashboardView
GET  /api/signals?limit=50        → list[Signal]
POST /api/backtest/runs           → BacktestJob (queued)
GET  /api/backtest/runs/{job_id}  → BacktestJob
POST /api/daemon/start            → DaemonStatus
POST /api/daemon/stop             → DaemonStatus
GET  /api/daemon/status           → DaemonStatus
```

---

## 9. 의존성

### 9.1 런타임

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.28,<1.0",
    "pydantic>=2.9,<3.0",
    "pydantic-settings>=2.6,<3.0",
    "pandas>=2.2,<3.0",
    "numpy>=1.26,<3.0",
    "structlog>=24.4,<26.0",
    "typer>=0.13,<1.0",
    "matplotlib>=3.9,<4.0",
    "jinja2>=3.1,<4.0",
    "rich>=13.9,<15.0",
    "pyarrow>=18.0,<22.0",
    "tenacity>=9.0,<10.0",
    "apscheduler>=3.10,<4.0",
    # v2.0 — 웹
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.32,<1.0",
    "python-multipart>=0.0.20,<1.0",
]
```

> 새 의존성 사유: `fastapi`(웹 프레임워크), `uvicorn[standard]`(ASGI 서버, websockets/uvloop 포함), `python-multipart`(form 파싱). `jinja2`는 v1에서 백테스트 리포트로 이미 포함.

### 9.2 개발

```toml
[dependency-groups]
dev = [
    "pytest>=8.3,<9.0",
    "pytest-asyncio>=0.24,<2.0",
    "pytest-cov>=6.0,<8.0",
    "pytest-vcr>=1.0,<2.0",
    "hypothesis>=6.115,<7.0",
    "ruff>=0.7,<1.0",
    "mypy>=1.13,<2.0",
    "pip-audit>=2.7,<3.0",
    "pandas-stubs>=2.2,<3.0",
    "freezegun>=1.5,<2.0",
]
```

> FastAPI TestClient는 `httpx`를 사용하므로 별도 추가 불필요(이미 런타임 의존).

---

## 10. 환경변수 / 설정

`.env.example`:

```ini
# 텔레그램
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# 화이트리스트 (적극형 20개 → 19개로 축소 2026-05-08, KRW-LTC 상장폐지로 제거)
WHITELIST_MARKETS=KRW-BTC,KRW-ETH,KRW-SOL,KRW-XRP,KRW-ADA,KRW-DOGE,KRW-AVAX,KRW-LINK,KRW-DOT,KRW-BCH,KRW-TRX,KRW-ATOM,KRW-NEAR,KRW-UNI,KRW-APT,KRW-ARB,KRW-OP,KRW-NEO,KRW-SHIB

# 전략 파라미터
BB_PERIOD=20
BB_STD_MULT=2.0
CCI_PERIOD=20
CCI_THRESHOLD_NORMAL=100
CCI_THRESHOLD_STRONG=200
VOLUME_RATIO_MIN_A=1.0
VOLUME_RATIO_MIN_B=1.5
SQUEEZE_LOOKBACK=120
SQUEEZE_QUANTILE=0.20

# 송출 정책
COOLDOWN_HOURS=2

# 운영
LOG_LEVEL=INFO
DRY_RUN=false

# v2.0 — 웹 대시보드
WEB_BIND=127.0.0.1                # 0.0.0.0으로 바꾸면 LAN 노출 → WEB_AUTH_PASSWORD 필수
WEB_PORT=8765
WEB_AUTH_PASSWORD=                # 빈 값 + 비-localhost 바인드 → 시작 거부
```

**가드:** `Settings` 검증 단계에서 `WEB_BIND != "127.0.0.1"` AND `not WEB_AUTH_PASSWORD` 인 경우 `SystemExit("WEB_BIND가 비-localhost인데 WEB_AUTH_PASSWORD가 설정되지 않았습니다. 외부 노출 시 비밀번호 필수.")`로 즉시 종료.

**설정 영속화 정책 (ADR-0008):** `state/settings.json`이 **단일 source of truth**. `.env`는 **첫 부팅 부트스트랩**(JSON 미존재 시 시드)에만 사용한다. GUI 저장은 항상 `state/settings.json`에 직렬화. 파일 권한 600(Windows는 사용자 단독 ACL). 시크릿 필드는 응답 마스킹.

```
부팅 시퀀스:
1. state/settings.json 존재 → JSON에서 로드
2. state/settings.json 미존재 → .env에서 로드 (메모리만, 자동 직렬화 X)
3. GUI 첫 저장 시 → state/settings.json 생성
4. 필수값 누락 → signal doctor 경고
```

`Settings`는 `pydantic-settings.BaseSettings`. `extra="ignore"`(Settings는 forbid 강제하지 않음).

---

## 11. CLI 인터페이스

```bash
# v2.0 권장: 웹 대시보드 + 라이브 루프 동시 실행
uv run signal serve
uv run signal serve --port 9000
uv run signal serve --bind 0.0.0.0          # WEB_AUTH_PASSWORD 미설정 시 거부

# 헤드리스 라이브 (CLI만)
uv run signal run
uv run signal run --dry-run

# 단발성 스캔
uv run signal scan-once --market KRW-BTC

# 백테스트 (CLI)
uv run signal backtest \
    --market KRW-BTC \
    --from 2025-01-01 --to 2026-04-30 \
    --mode A,B

# 캔들 사전 다운로드
uv run signal fetch-candles --market KRW-BTC --from 2025-01-01

# 점검
uv run signal doctor
```

종료 코드: 0(성공), 1(설정 오류), 2(네트워크 오류).

---

## 12. 테스트 전략

### 12.1 단위 (`tests/unit/`)
- 지표 정확성 (외부 레퍼런스 대비), 전략 BUY/SELL/None 케이스, 쿨다운(`freezegun`), Hypothesis property 테스트
- **(v2.0)** `test_settings_store.py` — JSON 저장/로드, 시크릿 마스킹

### 12.2 통합 (`tests/integration/`)
- `test_upbit_client.py` — `pytest-vcr` 카세트
- `test_backtest_engine.py` — 합성 시나리오
- **(v2.0)** `test_web_api.py` — FastAPI `TestClient`로 라우트 회귀
  - 설정 R/W 라운드트립, 마스킹 검증
  - `WEB_BIND=0.0.0.0` + 빈 비번 → 시작 거부
  - 백테스트 잡 큐 동시 1건 제한
  - 데몬 start/stop 토글 후 status 확인

### 12.3 CI 게이트
- `ruff check`, `ruff format --check`, `mypy src/` (strict), `pytest --cov-fail-under=70`, `pip-audit`

---

## 13. 운영 / 배포

### 13.1 실행

- **권장 (v2.0):** `uv run signal serve` — 웹 + 데몬 동일 프로세스. 브라우저 `http://localhost:8765`.
- 헤드리스: `uv run signal run` (nohup/tmux/systemd)

### 13.2 동시 구동 패턴

```python
# 개념도 — runner.py 또는 web/app.py
async def serve_combined(settings: Settings) -> None:
    config = uvicorn.Config(app, host=settings.web_bind, port=settings.web_port, log_config=None)
    server = uvicorn.Server(config)
    async with asyncio.TaskGroup() as tg:
        tg.create_task(server.serve())
        tg.create_task(run_signal_loop())
```

`asyncio.CancelledError`는 반드시 전파해 graceful shutdown. 데몬 stop/start는 별도 신호로 시그널 루프만 일시정지(웹 서버는 유지).

### 13.3 보안 기본선 (v2.0)

| 항목 | 정책 |
|------|------|
| 기본 바인드 | `127.0.0.1` (외부 차단) |
| 비-localhost 바인드 | `WEB_AUTH_PASSWORD` 필수, 미설정 시 시작 거부 |
| 인증 방식 | HTTP Basic (단일 비번). v1에서 OAuth/SSO 미지원 |
| 텔레그램 토큰 응답 | `••••••••XXXX` 마스킹 |
| 로그 토큰 | 마스킹 |
| CSRF | localhost 전용이라 v1에서 미적용. LAN 노출 시 `Origin` 검증 |

### 13.4 시간대 / 로그

- 모든 내부 처리 KST. `zoneinfo.ZoneInfo("Asia/Seoul")` timezone-aware
- structlog JSON 로그. 상관 키: `cycle_id`, `market`, `mode`, `direction`, `request_id`(웹 요청)
- 토큰 마스킹

### 13.5 .gitignore 핵심

```
.env
.env.*
__pycache__/
.mypy_cache/
.pytest_cache/
.ruff_cache/
data/
state/
reports/
*.log
htmlcov/
```

---

## 14. 마일스톤 / 구현 순서

| # | 마일스톤 | 산출물 | 검증 |
|---|---------|--------|------|
| 1 | 프로젝트 스캐폴딩 | `pyproject.toml`, `.env.example`, `signal doctor` | `signal doctor` 통과 |
| 2 | 도메인 모델 + 지표 | `models.py`, `enums.py`, `indicators/` | 단위 테스트 |
| 3 | 업비트 클라이언트 | `exchanges/upbit.py` + VCR | 통합 테스트 |
| 4 | 전략 모드 A | `strategies/bb_cci.py` | 합성 데이터 단위 테스트 |
| 5 | 전략 모드 B | 모드 B 추가 | 합성 데이터 단위 테스트 |
| 6 | 쿨다운 + 상태 | `state/cooldown.py` | freezegun 테스트 |
| 7 | 텔레그램 노티 | `notifiers/telegram.py` | dry-run 통합 테스트 |
| 8 | 차트 생성 | `charting/snapshot.py` + sendPhoto | 시각 검증 |
| 9 | 라이브 러너 | `runner.py` + `cli run` | 1시간 E2E |
| 10 | 백테스트 엔진 | `backtest/engine.py`, `metrics.py` | 합성 시나리오 단위 |
| 11 | 백테스트 리포트 | `report.py` HTML | 시각 검증 |
| 12 | 워크포워드 | `walkforward.py` | 단위 테스트 |
| **13** *(v2.0)* | **웹 백엔드 골격** | `web/app.py`, `web/api/*` 스켈레톤, `signal serve`, `state/settings_store.py`, `test_web_api.py` 기본 | TestClient로 모든 라우트 200/422 확인 |
| **14** *(v2.0)* | **설정·대시보드 페이지** | `templates/settings.html`, `templates/index.html`, Vanilla JS, 마스킹, dashboard 폴링 30s | 수동 시나리오: 설정 변경 → 검증 → 다음 사이클 반영 |
| **15** *(v2.0)* | **백테스트 페이지** | `templates/backtest.html`, `web/jobs.py` 큐, 진행률, 결과 차트 | 단일 백테스트 실행 → 결과 표시 |
| **16** *(v2.0)* | **데몬 제어 + 보안 기본선** | start/stop, `WEB_BIND`/`WEB_AUTH_PASSWORD` 가드, README 보안 섹션 | 비번 미설정 + 비-localhost → 거부 |

---

## 15. 열린 결정 / 리스크

### 15.1 열린 결정

- **(v1)** 차트 라이브러리(matplotlib vs mplfinance)
- **(v1)** 상태 저장소(JSON vs SQLite)
- **(v1)** 모드 A/B 동시 트리거 메시지 통합 여부
- **(v2.0)** 설정 영속화 형식: `.env` 자동 갱신 vs `state/settings.json` 별도 — **`state/settings.json` 추천**(GUI 저장에 안전, `.env`는 사용자 수동 편집용으로 보존)
- **(v2.0)** 자동 새로고침: 폴링 30s vs WebSocket — **폴링 추천**(단순). WebSocket은 P2
- **(v2.0)** 백그라운드 잡 큐: 인메모리 `asyncio.Queue` vs 파일 영속 — **인메모리**(재시작 시 진행 중 잡 손실 허용)

### 15.2 리스크

- **(v1)** API rate limit, 거래소 데이터 지연, 시그널 품질, 텔레그램 장애
- **(v2.0) GUI 보안**: `WEB_BIND=0.0.0.0` + 빈 비번 시 시크릿 노출 → 시작 거부 가드 필수
- **(v2.0) 시크릿 응답 누출**: GET /api/settings 응답에 토큰 평문이 섞이지 않도록 `SettingsView`/`SettingsUpdate` 분리
- **(v2.0) 백그라운드 잡 폭주**: 동시 백테스트 N개로 메모리/CPU 폭주 → 동시 1건 제한, 잡 시작 전 `state/active_jobs` 카운트 확인
- **(v2.0) GUI XSS**: 사용자 입력(화이트리스트, 코인명)을 Jinja2 자동 이스케이프 + JSON 응답만 제공으로 방어. `<script>` 인라인 금지

### 15.3 향후 확장 후보 (구현하지 않음)

- 다중 알림 채널 / 다중 거래소 / 추가 지표 / 포트폴리오 백테스트
- **(v2.0)** 데스크탑 패키지(Tauri/PyInstaller)
- **(v2.0)** 다국어 (ko/en)
- **(v2.0)** SaaS 호스팅 (별도 v3 PRD)

---

## 부록 A. Claude Code 작업 지침 (v2.0 갱신)

```
이 저장소의 PRD.md, DESIGN.md를 읽고 마일스톤 #N을 구현해줘.

규칙:
- DESIGN.md §8.1~8.5의 도메인 시그니처는 변경 금지
- §8.6 Web API 스키마는 신규 추가 — 자유롭게 구현하되 라우트/필드명 보존
- ~/.claude/CLAUDE.md (Clean Code 가이드)를 따름
- 새 의존성 추가 시 이유 설명
- public 함수에 타입 힌트 + Google 스타일 docstring
- 도메인 의미 있는 값은 config로 분리
- 하위 계층 except Exception 금지 (최상위 경계만 로깅과 함께 허용)
- 시크릿 마스킹 통과 못 하면 머지 금지 (테스트 필수)
- localhost 외 바인드 시 비번 강제 가드 필수

산출물:
1. 변경 파일 목록과 이유
2. 코드 + 테스트
3. README 업데이트(설치 가이드 / 보안 경고)가 필요하면 포함
4. 다음 마일스톤 전 확인할 점
```

---
---

### 8.7 워크포워드 결과 모델 (v2.0 — M12)

> M12에서 도입. §8.5 `BacktestResult`를 재사용하면서 fold별 + 합본 결과를 추가 모델로 표현. 이 모델들은 `walkforward.py`에서만 정의되며 다른 §8.x 영역과 독립.

\`\`\`python
# src/signal_program/backtest/walkforward.py
from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel, ConfigDict

@dataclass(frozen=True, slots=True)
class StrategyParams:
    """그리드 서치 대상 파라미터. v2.0은 BB·CCI·거래량 일부만 시작."""
    bb_std_mult: float
    cci_threshold_normal: int = 100
    volume_ratio_min_a: float = 1.0

class WalkforwardFold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    fold_index: int                       # 0부터 시작
    train_period_from: datetime           # KST tz-aware
    train_period_to: datetime
    validate_period_from: datetime
    validate_period_to: datetime
    best_params: StrategyParams           # 학습 구간 그리드 서치 결과
    train_result: BacktestResult          # 학습 구간 (참고용, in-sample)
    validate_result: BacktestResult       # 검증 구간 (out-of-sample, 신뢰값)

class WalkforwardResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    period_from: datetime                 # 전체 데이터 시작
    period_to: datetime                   # 전체 데이터 끝
    train_window_days: int                # 명시: 240 (8개월)
    validate_window_days: int             # 명시: 60 (2개월)
    folds: tuple[WalkforwardFold, ...]
    out_of_sample_combined: BacktestResult  # 검증 구간 trades만 합본
\`\`\`

**불변 규칙 (§8.5와 동일 레벨):**
- 위 세 모델의 필드 이름/타입/순서 변경 금지
- 새 필드 추가는 follow-up PR로
- `WalkforwardResult.out_of_sample_combined`는 검증 구간 trades 합본만. **학습 trades 절대 섞이지 않음** (data leakage 차단)
- `WalkforwardResult.period_from/to`는 전체 데이터 기간. `out_of_sample_combined.period_from/to`는 첫 fold validate_from ~ 마지막 fold validate_to
- MDD/Sharpe 컨벤션 §8.5 그대로 — 모델은 음수, 표시는 `abs()` / Sharpe는 부호 유지


> **이 문서는 살아있는 명세서다.** 변경 시 PR과 함께 PRD·DESIGN·README를 동기화한다.
