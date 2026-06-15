# Claude Code 지시문 — 시그널 카드 스파크라인 실데이터 배선 (로드맵 Now#2)

> **작성:** 2026-06-12 Cowork 설계 세션 · **갱신:** 2026-06-15 (코드 상태 점검 후 Task 1 기록 경로 교정)
> (`시그널 프로그램/plans/roadmap.md` Now#2, 범위 확정: 태민)
> **선행 조건:** v2.4.0 릴리스 **완료됨**(06-15, `a844ac0` + 태그 `v2.4.0`). 이 세션 변경분은 Unreleased에 쌓는다.
> **배경:** `SignalCardEntry.sparkline_prices`(schemas.py:232)는 v2.1부터 placeholder.
> `web/api/signals.py:97`이 항상 `sparkline_prices=None`, 카드의 `.mini-chart` SVG는
> 고정 점선 1줄 (`src/signal_program/web/templates/partials/signal_card.html:40~43`).
> **선행 숙지:** `CLAUDE.md` 변경 금지 영역. 봉 마감 close 기준·KST.

---

## 설계 결정 (Cowork 합의 — 변경하려면 중단·보고)

- **기록 시점 저장**: 시그널 발생 순간 runner가 이미 들고 있는 마감봉 close **최근 14개**를
  이력 레코드에 함께 저장한다. (읽기 시점 캔들 재조회는 페이지 로드마다 API 호출 유발 — 기각)
- **저장 위치는 레코드 레벨**: `{"signal": {...}, "sparkline_prices": [..14 floats..]}`.
  `Signal` 도메인 모델(§8.1 불변)은 건드리지 않는다.
- **하위 호환**: 키 없는 구버전 라인 → API가 `None` 반환 → 프런트는 현행 점선 placeholder 유지.
  과거 이력 백필 금지.

## Task 1 — 기록 경로 (TDD ★★)

> **2026-06-15 점검 교정:** 실제 기록 경로는 `SignalHistory.append`가 **아니다.** `SignalHistory.append`는
> 어디서도 호출되지 않는다(웹은 `read_recent` 읽기 전용, `RunnerHandle`도 읽기만). 진짜 write 경로는
> **`SignalLog.append`**(`state/signal_log.py:33`, async)이고, 러너가 `runner.py:139`
> `await self._signal_log.append(signal, sent_status, now)`로 쓴다. 레코드 형식은 이미
> `{"signal": {...}, "sent_status":..., "sent_at":...}` → `"sparkline_prices"` 추가가 그대로 맞는다.

1. `SignalLog.append` 시그니처 확장: `append(signal, sent_status, sent_at, sparkline_prices=None)`
   (기본 None — 기존 호출부 무수정 호환). 레코드 dict(`signal_log.py:36~`)에 키 포함.
2. `runner.py:139` 호출부에서 close 14개 전달. 같은 스코프에 `df = candles_to_df(candles).iloc[:-1]`
   (`runner.py:103`)가 살아 있으므로 `df["close"].tail(14).tolist()`로 추출(14개 미만이면 있는 만큼).
   쿨다운 경로(`runner.py:111`, `"cooled_down"`)는 카드 미표시이므로 `None` 유지(전달 안 함).
3. 테스트: ① append가 prices 키를 기록, ② 미전달 시 키 생략(또는 null), ③ 기존 레코드 포맷 회귀 없음.

## Task 2 — API 배선

- `web/api/signals.py` 카드 빌드 루프: `record.get("sparkline_prices")` →
  `SignalCardEntry.sparkline_prices` (tuple 변환, 키 없으면 None).
- 테스트: 신·구 레코드 혼재 jsonl로 read → 신형만 prices 채워지는지 1건.

## Task 3 — 프런트 렌더 (결정됨: A1 — 테이블 8번째 열)

> **2026-06-15 렌더 타깃 결정 (태민):** `signal_card.html` 매크로는 orphan(어떤 페이지도 미포함),
> 실사용 화면은 `dashboard.js`의 7열 테이블 하나뿐임을 확인. → **A1: 테이블에 sparkline 열을 추가한다.**
> (B안 — 카드 매크로 부활/레이아웃 전환 — 은 범위 제외된 별도 트랙. `signal_card.html`은 건드리지 않는다.)

대상 화면은 코인 테이블(`#signal-table`)과 국장 테이블(`#kr-signal-table`) **양쪽**이다.

1. **헤더 추가** — `templates/index.html` 두 `<thead>` 모두(시각 `<th>` 뒤)에 정렬 불가 `<th>추세</th>`
   추가(`data-sort-key`·`onclick` 없음 — sparkline은 정렬 대상 아님). 2곳.
2. **행 셀 추가** — `dashboard.js` `renderTable()`의 `tr.innerHTML`에 8번째 `<td>` 추가(시각 td 뒤).
   - `sig.sparkline_prices` 있으면: min/max 정규화 → viewBox `0 0 100 40` 인라인 `<svg>` + `<polyline>`
     (라이브러리 금지). stroke는 기존 CSS 변수 재사용(예: 방향색/`--color-*`), 다크 모드 양쪽 확인.
   - 없으면(None/빈 배열): 현행 점선 placeholder와 동일한 1줄 SVG(`stroke-dasharray="3,3"`) 유지.
   - 데이터 출처는 `/api/signals/cards` 응답(Task 2에서 `sparkline_prices` 채워짐).
3. **펼침 행 colspan 보정 (필수)** — `buildDetailRow()`의 `td.colSpan = 7` → **`8`**
   (dashboard.js:401). 안 바꾸면 detail 행이 한 칸 어긋난다.

## 범위 제한 (하지 말 것)

- `Signal` 등 §8.1~8.5 도메인 시그니처 수정
- signal_card partial ↔ dashboard.js 중복 해소 리팩토링 (별도 트랙)
- 차트 라이브러리·신규 의존성 추가 (인라인 SVG로 충분)
- 과거 jsonl 백필 스크립트
- 읽기 시점 캔들 조회 폴백 ("없으면 점선"이 정답 — 조용한 API 호출 추가 금지)

## 완료 기준 (품질 게이트)

```bash
uv run ruff check src/ --fix && uv run ruff format src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
```

- [ ] Task 1~2 테스트 4건 + 기존 테스트 전부 통과
- [ ] 수동 확인: `signal serve` → 대시보드 테이블 '추세' 열에서 신규 시그널 폴리라인 / 구 시그널 점선 공존 (코인·국장 양쪽)
- [ ] `CHANGELOG.md` Unreleased 항목 추가
- [ ] 커밋 분리: ① 기록+API(+테스트), ② 프런트 렌더

## 세션 시작 명령

```powershell
cd C:\Users\user3\Desktop\VibeCoding\signal-up
claude "docs/prompts/sparkline-realdata-prompt.md 를 읽고 그대로 수행해줘"
```
