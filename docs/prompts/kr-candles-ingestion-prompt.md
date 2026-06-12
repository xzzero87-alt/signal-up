# Claude Code 지시문 — 국장 60분봉 히스토리 적재 (Phase B 선행 스파이크 + 조건부 구현)

> **작성:** 2026-06-11 Cowork 설계 세션
> **배경:** 전략 비교 매트릭스 Phase B(삼성전자 005930·SK하이닉스 000660·삼성전기 009150).
> 백테스트 엔진은 마켓 중립(`data/candles/{market}/60/*.parquet`만 있으면 동작)이나
> `fetch-candles`가 업비트 전용이라 국장 적재 경로가 없다.
> 설계 문서: `시그널 프로그램/plans/strategy-comparison-matrix.md` §2 Phase B.
> **독립 트랙:** strategy-owned-exit / walkforward 핸드오프와 의존성 없음, 병렬 진행 가능.
> **범위 축소 (2026-06-11 로드맵 결정):** 이번 세션은 **Task 1(스파이크)까지만** 수행하고 종료.
> Task 2(fetch-kr-candles 구현·적재)는 스파이크 결과 + Phase B 재논의(plans/roadmap.md Next) 통과 후 별도 세션.
> **선행 숙지:** `CLAUDE.md` 변경 금지 영역. 자동매매 금지(ADR-0002). KIS 키는 `.env`에서만, 로그 마스킹.

---

## Task 1 — 스파이크: KIS 60분봉 과거 도달 한계 실측 (코드 머지 없음)

**이것이 게이트다. 결과에 따라 Task 2 진행 여부가 갈린다.**

1. 기존 `KisApiAdapter`(`exchanges/kis_api.py`, 페이지네이션 `_fetch_60m_candles`)를 일회성
   스크립트로 호출 — 005930 60분봉을 과거로 최대한 거슬러 수집
2. **기록:** 실제 도달 가능한 가장 오래된 봉 시각, 호출 수, rate limit 체감, 누락 구간 유무
3. 결과를 `docs/prompts/kr-candles-spike-result.md`에 3~10줄로 기록 (커밋 1개)

**판정:**

- 2025-01-01까지 도달 → Task 2 진행
- 부분 도달 (예: 최근 N개월만) → 도달 범위 기록 후 Task 2 진행하되 적재는 가능 범위만
- 사실상 불가 (수일~수주만) → **여기서 중단, 보고.** 대안(일봉 비교 다운그레이드 / 외부 소스)은
  Cowork 설계 세션에서 결정 (멋대로 외부 의존성 추가 금지)

## Task 2 — fetch-kr-candles 명령 (조건부, TDD ★★)

- `cli.py`에 `fetch-kr-candles` 명령 신규: `--symbol 005930 --from --to`
  (기존 `fetch-candles`와 별도 명령 — 업비트 경로에 분기 섞지 말 것)
- `KisApiAdapter` 재사용, 저장은 기존 `backtest/candles_io.save_candles`로
  `data/candles/{symbol}/60/{YYYY-MM}.parquet` — **업비트와 동일 포맷/경로 규약** (엔진 무수정으로 백테스트 호환)
- 국장 특성 처리:
  - 장 운영시간 봉만 존재 (하루 7봉 내외) — 갭은 정상, 보간 금지
  - KST tz-aware (도메인 규칙), 휴장일 빈 달 허용
  - rate limit: 어댑터 기존 정책 따름, 추가 sleep이 필요하면 기존 상수 재사용
- 테스트: 어댑터 mock으로 ① 월 분할 저장 경로, ② 빈 응답 처리, ③ 기간 필터 — 3건
  (실 API 호출 테스트 금지 — 키 필요. 스파이크에서 이미 실측함)
- 적재 실행: 3종목 × 도달 가능 범위 전체 → 각 종목 parquet 파일 목록을 커밋 메시지에 기록
  (parquet 자체는 기존 data/ 정책 따름 — `data/candles/`가 git 추적 중인지 확인 후 동일하게)

## 범위 제한 (하지 말 것)

- `scripts/strategy_matrix.ps1` 마켓 추가 — Cowork 산출물이므로 데이터 확보 보고 후 Cowork에서 수정
- 백테스트 엔진·전략 코드 수정 (이 트랙은 데이터 적재만)
- pykrx 등 신규 의존성 추가 — Task 1 결과 보고 없이 금지 (CLAUDE.md 의존성 규칙)
- KIS 실서버/모의 구분: 기존 `kis_is_paper` 설정 따름, 변경 금지

## 완료 기준 (품질 게이트)

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] 스파이크 결과 문서 (도달 한계 명시)
- [ ] (조건부) fetch-kr-candles + 테스트 3건 + 3종목 적재
- [ ] `CHANGELOG.md` Unreleased 항목 추가
- [ ] 커밋 분리: ① 스파이크 결과 문서, ② 명령+테스트, ③ 적재 산출물 기록

## 세션 시작 명령

```powershell
cd C:\Users\user3\Desktop\VibeCoding\signal-up
claude "docs/prompts/kr-candles-ingestion-prompt.md 를 읽고 그대로 수행해줘"
```
