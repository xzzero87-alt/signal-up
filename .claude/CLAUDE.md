# CLAUDE.md — 업비트 시그널 프로그램 (프로젝트 가이드)

> 이 파일은 **이 프로젝트에 진입하는 Claude Code/Cowork**가 가장 먼저 읽는 진입점입니다.
> 글로벌 코딩 가이드(`~/.claude/CLAUDE.md`)를 우선 따르고, 본 파일은 이 프로젝트만의 추가 규칙입니다.

## 진입점 문서

순서대로 훑어보세요.

1. [`../PRD.md`](../PRD.md) — Product Requirements (v2.2)
2. [`../DESIGN.md`](../DESIGN.md) — 기술 명세서 (v2.0)
3. [`../docs/adr/README.md`](../docs/adr/README.md) — Architecture Decision Records 인덱스 (0001~0008)
4. [`../docs/CLAUDE_CODE_PROMPTS.md`](../docs/CLAUDE_CODE_PROMPTS.md) — **마일스톤별 Claude Code 지시문** (1~16 + 일반 패턴)

## 변경 금지 영역 (Hard Lines)

- **DESIGN.md §8.1~8.5의 Pydantic 도메인 시그니처** — `Candle`, `IndicatorSnapshot`, `Signal`, `Strategy`/`Exchange`/`Notifier` Protocol, `TradeRecord`, `BacktestResult`. 신규 필드/모델 추가는 허용, 기존 시그니처 수정 금지.
- **자동매매(주문 실행) 코드** — [ADR-0002](../docs/adr/0002-no-autotrading.md). v1·v2 모두 제외.
- **외부 인터넷에 노출되는 SaaS 호스팅** — [ADR-0006](../docs/adr/0006-self-hosted-distribution.md). v3 별도 프로젝트.

## 핵심 도메인 규칙

- 모든 시그널 평가는 **봉 마감 가격(close) 기준**, 진행 중 봉(미마감) 제외.
- 시간대는 항상 KST(`Asia/Seoul`). `datetime` 객체는 timezone-aware.
- 텔레그램 토큰 등 시크릿은 로그·응답에서 마스킹(`••••••••XXXX`).
- 웹 바인드 기본 `127.0.0.1`. `0.0.0.0`로 바꾸려면 `WEB_AUTH_PASSWORD` 환경변수 필수 (미설정 시 시작 거부).

## 핵심 명령

```bash
# 운영
uv run signal serve              # GUI + 데몬 (v2.0 권장)
uv run signal run                # 헤드리스
uv run signal scan-once --market KRW-BTC
uv run signal backtest --market KRW-BTC --from 2025-01-01 --to 2026-04-30
uv run signal doctor             # 환경 점검

# 품질 게이트 (CI에서 강제)
uv run ruff check src/ --fix
uv run ruff format src/
uv run mypy src/                 # strict
uv run pytest --cov=src/ --cov-fail-under=70
uv run pip-audit
```

## 마일스톤 진행 상황

DESIGN.md §14 참조. 총 16단계.
- 1~12: v1 코어 (스캐폴딩 → 워크포워드)
- 13~16: GUI v2.0 (웹 백엔드 → 설정·대시보드 → 백테스트 페이지 → 데몬 제어)

## ADR 추가 시

1. [`docs/adr/template.md`](../docs/adr/template.md) 복제 → 다음 일련번호 (`docs/adr/0008-...`)
2. [`docs/adr/README.md`](../docs/adr/README.md) 인덱스 표에 행 추가
3. 결정 변경 시 기존 ADR을 `superseded by ADR-NNNN`으로 표시 (삭제 금지)
4. PR 본문에 새 ADR 링크 포함

## 의존성 추가 시

- `pyproject.toml` 수정 + `uv sync` + 커밋. `uv.lock`도 같이 커밋.
- PR/커밋 메시지에 추가 사유와 대안 검토 결과 명시.
- 기존 의존성과 중복되는지 먼저 확인 (예: `httpx`는 이미 있음 → 새로 추가 금지).

## 적용된 외부 스킬

이 프로젝트는 다음 스킬의 가이드를 명시적으로 따릅니다.

| 영역 | 스킬 |
|------|------|
| PRD 작성 | `product-management:write-spec` |
| ADR 작성 | `engineering:architecture` + `everything-claude-code:architecture-decision-records` |
| 코드 품질 | 사용자 글로벌 `~/.claude/CLAUDE.md` (Clean Code 가이드) |
| Hooks | `~/.claude/CLAUDE.md` §28.3 — `.claude/settings.json`에 적용 |

추후 코드 작성 단계에서 추가로 활용 가능한 스킬은 [`PRD.md` 부록 B](../PRD.md) 참조.

## 첫 진입자를 위한 빠른 체크리스트

- [ ] `~/.claude/CLAUDE.md` 글로벌 가이드를 읽음
- [ ] PRD.md, DESIGN.md, docs/adr/README.md 훑어봄
- [ ] 변경 금지 영역(이 문서 위쪽) 인지
- [ ] `uv sync`로 의존성 동기화 (코드 단계 진입 시)
- [ ] `.env` 작성 ([`../DESIGN.md` §10](../DESIGN.md))
- [ ] `uv run signal doctor`로 환경 점검 (구현 후)
