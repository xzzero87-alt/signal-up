# 업비트 시그널 프로그램

> **업비트 KRW 마켓**의 1시간봉 시그널을 **볼린저 밴드 + CCI** 전략으로 자동 감지해 **텔레그램**으로 알림하고, 동일 전략을 **백테스트**로 사전 검증하는 자가설치 도구.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: TBD](https://img.shields.io/badge/license-TBD-yellow.svg)](#라이선스)
[![Status: Pre-release](https://img.shields.io/badge/status-pre--release-orange.svg)](#)

⚠️ **참고용 시그널 도구입니다.** 자동매매·주문 실행 기능은 **포함되어 있지 않습니다**. 매매 결정과 책임은 사용자 본인에게 있습니다.

---

## 무엇을 해주는가

- **24/7 모니터링 부담 제거** — 1시간봉 마감마다 화이트리스트 코인을 자동 평가
- **검증 가능한 수치 전략** — 블랙박스 없음. 모든 임계값(BB period, CCI ±100/±200 등)이 노출·튜닝 가능
- **두 가지 시그널 모드 동시 실행** — 평균회귀(A) + 스퀴즈 돌파(B) 분기 평가
- **텔레그램 차트 첨부** — BB·CCI 시각 컨텍스트를 메시지와 함께 모바일 즉시 수신
- **동일 전략으로 백테스트** — 워크포워드 분할로 과적합 최소화
- **로컬 웹 대시보드** — 설정/시그널 모니터링/백테스트/데몬 제어를 브라우저에서. 외부 인터넷 노출 없음
- **오픈소스 자가설치** — 자기 PC에 설치, 자기 텔레그램 봇 토큰. 시크릿이 외부로 나가지 않음

---

## Quick Start (5분)

### 사전 준비

| 항목 | 권장 |
|------|------|
| OS | Windows / macOS / Linux |
| Python | 3.11+ |
| 패키지 매니저 | [uv](https://docs.astral.sh/uv/) |
| Git | 최신 안정판 |

```bash
# uv 설치 (한 번만)
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 1. 텔레그램 봇 만들기 (1분)

> **첫 사용 시에만 필요.** 이미 봇이 있다면 [2단계](#2-저장소-내려받기)로 넘어가세요.

1. 텔레그램에서 [@BotFather](https://t.me/BotFather)를 검색하고 대화 시작
2. `/newbot` 입력 → 봇 이름과 username 지정 → **HTTP API 토큰** 발급 (예: `1234567890:AAFx...`)
3. 만든 봇과 대화방을 시작 (`/start` 한 번 보내기)
4. 본인의 `chat_id` 확인:
   - 텔레그램에서 [@userinfobot](https://t.me/userinfobot) 대화 → 본인 user ID(=chat_id) 회신 받음
   - 또는 브라우저에서 `https://api.telegram.org/bot<TOKEN>/getUpdates` 접속

### 2. 저장소 내려받기

```bash
git clone <repo-url> upbit-signal
cd upbit-signal
uv sync          # 의존성 동기화 (uv.lock 기준)
```

### 3. 환경변수 설정

```bash
cp .env.example .env
# 에디터로 .env 열어 아래 두 값만 입력
```

```ini
TELEGRAM_BOT_TOKEN=1234567890:AAFx...   # 1단계에서 발급
TELEGRAM_CHAT_ID=123456789              # 1단계에서 확인
```

> 그 외 키(화이트리스트, 임계값 등)는 기본값으로 동작합니다. 나중에 GUI에서 변경 가능.

### 4. 환경 점검

```bash
uv run signal doctor
```

- 업비트 API 핑 ✅
- 텔레그램 API 핑 ✅
- 화이트리스트 코인 존재 여부 ✅

### 5. 실행

```bash
uv run signal serve
```

브라우저에서 [http://localhost:8765](http://localhost:8765) 접속. 다음 1시간봉 마감 시점에 첫 시그널이 평가됩니다.

---

## 사용법

### CLI

```bash
uv run signal serve              # 웹 대시보드 + 백그라운드 데몬 (권장)
uv run signal serve --port 9000  # 포트 변경
uv run signal run                # 헤드리스 라이브 (대시보드 없음)
uv run signal run --dry-run      # 텔레그램 송출 없이 로직만 검증
uv run signal scan-once --market KRW-BTC          # 단발 평가
uv run signal backtest --market KRW-BTC \
    --from 2025-01-01 --to 2026-04-30 --mode A,B  # 백테스트
uv run signal fetch-candles --market KRW-BTC --from 2025-01-01  # 캔들 사전 다운로드
uv run signal doctor             # 환경 점검
```

### 웹 대시보드 (4페이지)

| 페이지 | 기능 |
|--------|------|
| **시그널 대시보드** (`/`) | 데몬 상태, 코인별 BB/CCI 현재값, 최근 50건 시그널 |
| **설정** (`/settings`) | 화이트리스트, BB/CCI 임계값, 텔레그램 토큰(마스킹), dry-run 토글, 검증 버튼 |
| **백테스트** (`/backtest`) | 코인·기간·모드 입력 → 비동기 실행 → 진행률 + 결과 차트 |
| **데몬 제어** (`/`의 카드) | Start/Stop 토글, 다음 평가 시각, 최근 사이클 상태 |

### 시그널 메시지 예시

```
🟢🟢 [BUY-Strong] KRW-BTC (1h) — Mode A
가격: 95,200,000 KRW (-1.42%)
BB: 위치 -1.05σ (하단 이탈)
CCI(20): -213
거래량: 평균의 2.1배
시각: 2026-05-07 14:00 KST

📊 차트 첨부 (PNG)
ℹ️ 참고용 시그널 — 매매는 직접 판단
```

---

## 설정

### `.env` (첫 부팅 부트스트랩)

전체 키 목록은 [`.env.example`](.env.example) 참조. 핵심:

```ini
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WHITELIST_MARKETS=KRW-BTC,KRW-ETH,...
BB_PERIOD=20
CCI_THRESHOLD_NORMAL=100
COOLDOWN_HOURS=2
WEB_BIND=127.0.0.1
WEB_PORT=8765
```

### `state/settings.json` (런타임 source of truth)

GUI에서 저장하는 모든 설정은 `state/settings.json`에 영속화됩니다. `.env`는 이 파일이 없을 때만 시드로 읽힙니다([ADR-0008](docs/adr/0008-settings-storage.md)).

> **수동 편집은 `.env`로, GUI는 `state/settings.json`으로**. 둘이 충돌하면 `state/settings.json`이 이깁니다.

### `state/`는 절대 git에 커밋하지 마세요
시크릿(텔레그램 토큰)이 들어 있습니다. `.gitignore`에 이미 명시되어 있지만 확인 권장.

---

## ⚠️ 보안 경고

### 기본값 — 안전

```ini
WEB_BIND=127.0.0.1   # localhost 전용. 외부 접속 차단
WEB_AUTH_PASSWORD=   # (비어 있어도 OK)
```

이 기본값으로는 같은 PC 사용자만 대시보드에 접속할 수 있습니다.

### LAN 노출 — 비밀번호 필수

```ini
WEB_BIND=0.0.0.0
WEB_AUTH_PASSWORD=<강한 비밀번호>
```

> **`WEB_BIND`가 `127.0.0.1`이 아닌데 `WEB_AUTH_PASSWORD`가 비어 있으면 시작 거부됩니다.** 시크릿 노출 방지 가드.

### 인터넷 노출은 비추천

본 프로젝트는 **자가설치 단일 사용자**를 가정합니다. 인터넷에 직접 노출하지 마세요. 멀티유저/SaaS가 필요하면 별도 v3 프로젝트로 분리될 예정입니다([ADR-0006](docs/adr/0006-self-hosted-distribution.md)).

### 시크릿 마스킹

- 텔레그램 토큰은 GUI 응답에서 `••••••••XXXX` 형태로 마스킹
- 로그에도 마스킹 적용
- 토큰 유출 의심 시: 텔레그램 [@BotFather](https://t.me/BotFather) → `/revoke` → 새 토큰 발급

---

## 트러블슈팅

### `signal doctor`가 텔레그램 API 실패를 보고

- `.env`의 `TELEGRAM_BOT_TOKEN` 형식 확인 (`숫자:문자열` 형태)
- 봇과 대화방을 한 번 이상 시작했는지 확인 (`/start`)
- 방화벽이 `api.telegram.org` 송신을 막지 않는지 확인

### 시그널이 안 옴

1. `signal doctor` 통과 여부
2. `dry_run=false`인지 (`.env` 또는 GUI 설정)
3. 데몬이 Running 상태인지 (대시보드 카드)
4. 1시간봉 마감 시점(KST 정각 +30~90초)이 지났는지
5. 쿨다운 정책: 같은 코인+같은 모드+같은 방향은 2시간에 1회만 송출. `state/cooldown.json` 확인

### 업비트 rate limit 에러

화이트리스트가 너무 큰 경우(20개 초과) 발생할 수 있음. 동시 요청은 자동으로 5개 이하로 제한되지만, 백테스트 fetch-candles는 더 보수적으로 돌리세요:

```bash
uv run signal fetch-candles --market KRW-BTC --from 2025-01-01  # 한 번에 1코인
```

### 웹 대시보드가 안 열림

- `lsof -i :8765` (또는 Windows: `netstat -ano | findstr :8765`)로 포트 충돌 확인
- `signal serve --port 9000`으로 다른 포트 사용
- 방화벽 예외 추가

### 백테스트 결과가 비현실적으로 좋음

워크포워드 모드(`--walkforward`)로 다시 돌려 검증 구간 결과만 보세요. 학습 구간만 보면 과적합된 임계값에 속을 수 있습니다.

---

## 프로젝트 구조

```
upbit-signal/
├── src/signal_program/      # 소스 코드 (마일스톤별 점진 추가)
│   ├── indicators/          # BB, CCI 순수 함수
│   ├── strategies/          # BB+CCI 모드 A/B
│   ├── exchanges/           # 업비트 클라이언트
│   ├── notifiers/           # 텔레그램 봇
│   ├── backtest/            # 시뮬레이터, 워크포워드, 리포트
│   ├── web/                 # FastAPI 백엔드 + 정적 프런트엔드
│   └── ...
├── tests/                   # 단위 + 통합
├── docs/adr/                # Architecture Decision Records (8개)
├── data/                    # parquet 캔들 캐시 (gitignore)
├── state/                   # 쿨다운, 설정, 차트 (gitignore)
├── reports/                 # 백테스트 HTML (gitignore)
├── PRD.md                   # Product Requirements (v2.2)
├── DESIGN.md                # 기술 명세서 (v2.0)
└── README.md                # 이 문서
```

> 코드는 마일스톤(1~16) 단위로 점진적으로 추가됩니다. 자세한 마일스톤은 [DESIGN.md §14](DESIGN.md) 참조.

---

## 개발 / 기여

```bash
# 개발 의존성 포함 동기화
uv sync --dev

# 품질 게이트 (PR 머지 전 필수)
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/
uv run mypy src/                      # strict
uv run pytest --cov=src/ --cov-fail-under=70
uv run pip-audit                      # 의존성 취약점 검사
```

### 코딩 표준
- Python 3.11
- 타입 힌트 필수 (public 함수)
- Pydantic v2 도메인 모델 (`frozen=True, extra="forbid"`)
- structlog 구조화 로그 + 상관 키
- 자세한 규칙: [`~/.claude/CLAUDE.md`](https://github.com/) (Clean Code 가이드)

### 변경 금지 영역 (Hard Lines)
- `DESIGN.md §8.1~8.5` 도메인 시그니처 — 신규 필드 추가만 허용
- 자동매매 코드 — [ADR-0002](docs/adr/0002-no-autotrading.md)
- 외부 인터넷 SaaS 호스팅 — v3 별도 프로젝트

### Pull Request 가이드
1. 마일스톤 단위 PR (DESIGN.md §14)
2. 새 의존성은 PR 본문에 사유 명시
3. 새 결정은 [`docs/adr/`](docs/adr/)에 ADR 추가 (`template.md` 복제)
4. 품질 게이트 모두 통과
5. 보안 가드(localhost 외 바인드 시 비번 강제) 회귀 테스트

---

## 문서

| 문서 | 내용 |
|------|------|
| [`PRD.md`](PRD.md) | 제품 요구사항, 사용자 스토리, 성공 지표, ADR 인덱스 |
| [`DESIGN.md`](DESIGN.md) | 기술 명세, 아키텍처, 도메인 모델, REST API, 마일스톤 |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records 8건 |
| [`.claude/CLAUDE.md`](.claude/CLAUDE.md) | Claude Code 진입점·변경 금지 영역 |

---

## 라이선스

**TBD** — 현재 미정 ([Q10](PRD.md)). v1 공개 직전 결정 예정. MIT 라이선스를 권장.

---

## Disclaimer

본 도구는 **시그널 알림 + 백테스트 도구**이며, 다음을 포함하지 않습니다:

- ❌ 자동매매 / 주문 실행
- ❌ 투자 자문 / 매매 권유
- ❌ 수익 보장

시그널은 **참고용 의사결정 보조 정보**입니다. 매매 결정과 그로 인한 손익은 사용자 본인에게 귀속됩니다. 백테스트 결과는 과거 데이터 기반이며 미래 수익을 보장하지 않습니다.

---

## 로드맵

| 단계 | 상태 |
|------|------|
| v1 코어 (CLI + 텔레그램 + 백테스트) | 🚧 마일스톤 1~12 |
| v2 GUI (FastAPI 로컬 대시보드) | 🚧 마일스톤 13~16 |
| v3 SaaS / 데스크탑 패키지 | 📋 별도 프로젝트로 검토 |

자세한 진행 상황은 [DESIGN.md §14](DESIGN.md)와 GitHub Issues 참조.
