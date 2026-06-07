# UI 작업 진입점 (UI Guide)

> **UI 작업자(사람·에이전트)가 가장 먼저 읽는 단일 파일.**
> 이 문서 하나로 작업 착수가 가능해야 한다. 관련: [`collaboration-prd.md`](collaboration-prd.md) (PRD) · [`agent-roles.md`](agent-roles.md) (에이전트 소집 템플릿) · [`../ui-redesign-spec.md`](../ui-redesign-spec.md) (M18 디자인 명세)
> 라이브 컴포넌트 확인: 서버 실행 후 `/_styleguide` 접속.

활성 코드베이스: `C:\Users\user3\Desktop\VibeCoding\signal-up` (Git 저장소).
프론트엔드 스택: **FastAPI + Jinja2(SSR) + Vanilla JS + CSS 변수**. 프레임워크·외부 CDN 없음.

---

## 1. 파일 맵

```
src/signal_program/web/
├── templates/
│   ├── base.html              # 공통 레이아웃 (topbar/sidebar/테마 토글/시계). 모든 페이지가 extends
│   ├── index.html             # 대시보드 (시그널 테이블)
│   ├── settings.html          # 설정 (전략 파라미터 아코디언·텔레그램·국장 API)
│   ├── backtest.html          # 백테스트
│   ├── failures.html          # 알림 실패
│   ├── system.html            # 시스템 (데몬 제어·로그)
│   └── partials/signal_card.html
├── static/
│   ├── css/app.css            # ★ 단일 스타일시트 (다크 기본 + 라이트 토글)
│   └── js/
│       ├── dashboard.js        # index.html 전용 (폴링·필터·렌더)
│       ├── settings.js         # settings.html 전용 (저장·검증·토스트)
│       └── backtest.js         # backtest.html 전용
└── api/
    ├── pages.py               # ★ HTML 페이지 라우트 (아래 매핑 참조)
    ├── settings.py            # GET/PUT /api/settings
    ├── dashboard.py · signals.py · charts.py · backtest.py
    ├── kr_dashboard.py · failures.py · feedback.py · daemon.py · health.py
```

## 2. 페이지 ↔ 템플릿 ↔ JS ↔ API 매핑

| 경로 | 템플릿 | 전용 JS | 주요 API | 라우트 정의 |
|------|--------|---------|----------|-------------|
| `/` | `index.html` | `dashboard.js` | `/api/dashboard`, `/api/signals/cards`, `/api/kr/signals` | `pages.py:index` |
| `/settings` | `settings.html` | `settings.js` | `GET·PUT /api/settings` | `pages.py:settings_page` |
| `/backtest` | `backtest.html` | `backtest.js` | `POST /api/backtest` | `pages.py:backtest_page` |
| `/failures` | `failures.html` | (인라인) | `/api/failures` | `pages.py:failures_page` |
| `/system` | `system.html` | (인라인) | `/api/daemon`, 로그 | `pages.py:system_page` |
| `/_styleguide` | `styleguide.html` | (인라인) | 없음 (정적 렌더) | `pages.py:styleguide_page` · 개발 전용, `SIGNAL_STYLEGUIDE=0`으로 비활성 |

HTML 페이지 라우트는 모두 `api/pages.py`에 모여 있다. 새 페이지 추가 시 여기에 라우트 + `templates/`에 파일 + (필요 시) `static/js/`에 전용 스크립트.

## 3. 변경 금지 / 주의 영역 (Hard Lines)

### 3.1 `settings.js` 의존 속성 — 디자인을 바꿔도 반드시 보존
설정 폼은 JS가 DOM 속성으로 필드를 식별한다. 디자인(레이아웃·클래스·래퍼)은 자유롭게 바꿔도, **다음 속성은 그대로 유지**해야 저장이 깨지지 않는다.

- 입력 요소의 `id="{field}"` 와 `name="{field}"` (예: `id="bb_period" name="bb_period"`)
- 에러 표시용 `id="err-{field}"` 스팬
- `data-field="{field}"` (검증 표시에 사용)
- 라디오 그룹 `name="strategy_version"` (`updateV2Dim()` 토글이 의존)

필드 타입 집합은 `settings.js` 상단에 정의됨 (`STRING_FIELDS` / `INT_FIELDS` / `FLOAT_FIELDS` / `CHECKBOX_FIELDS`). **새 설정 필드 추가 시 이 집합에도 등록**해야 타입 변환이 맞는다.

### 3.2 도메인 규칙 (UI에도 영향)
- 매수=빨강(`--color-buy`), 매도=파랑(`--color-sell`) — 한국 관행. 반전 금지.
- 시각 표기는 KST.
- 시크릿(토큰·키)은 `type="password"` + placeholder 마스킹 유지.

## 4. `<script>` 배치 규칙

- **공통 동작**(테마 토글, 시계, 데몬 상태)은 `base.html` 인라인 `<script>`에 둔다.
- **페이지 전용 로직**은 `static/js/{page}.js`로 분리하고 `{% block scripts %}`에서 로드한다.
- 현재 `settings.html` 등 일부 템플릿에 페이지 전용 인라인 스크립트(`updateV2Dim`, `stepField`)가 남아 있다. 신규 코드는 가능하면 전용 `.js`로 작성한다. 기존 인라인은 동작하므로 무리하게 옮기지 않는다 (surgical changes 원칙).

## 5. 디자인 토큰 (단일 소스)

**`app.css`의 `:root`가 모든 색상·간격·radius의 유일한 출처다.** 컴포넌트 CSS·인라인 style에 색상 리터럴(`#xxxxxx`, `rgba(...)`)을 직접 쓰지 말고 항상 `var(--token)`을 쓴다. (예외: 토큰 정의부 자신, `:root`/`[data-theme]` 블록)

### 색상 토큰

| 토큰 | 다크 | 라이트 | 용도 |
|------|------|--------|------|
| `--color-bg` | `#13161c` | `#f4f6fa` | 메인 배경 |
| `--color-surface` | `#1a1e26` | `#ffffff` | 사이드바·상단바·카드 |
| `--color-surface-2` | `#222732` | `#f7f9fc` | hover·인풋 배경 |
| `--color-surface-3` | `#2a3140` | `#eef1f6` | 스텝퍼 버튼 hover 등 한 단계 더 |
| `--color-border` | `#2c333f` | `#e2e7ef` | 기본 구분선 |
| `--color-border-2` | `#39414f` | `#cfd6e0` | 강조 구분선·인풋 테두리 |
| `--color-text` | `#e4e8ee` | `#1a1f29` | 본문 텍스트 |
| `--color-muted` | `#9aa4b2` | `#5a6573` | 보조 텍스트 |
| `--color-muted-2` | `#5b6573` | `#8b95a4` | 더 흐린 라벨 |
| `--color-primary` | `#1463ff` | (동일) | 강조 파랑 (업비트풍) |
| `--color-primary-soft` | `rgba(20,99,255,.12)` | `rgba(20,99,255,.08)` | 활성 메뉴·태그 배경 |
| `--color-buy` | `#f04452` | (동일) | 매수/상승 (한국 관행: 빨강) |
| `--color-buy-bg` / `-border` | rgba 0.10 / 0.35 | rgba 0.07 / 0.30 | 매수 배지 배경·테두리 |
| `--color-sell` | `#3b82f6` | (동일) | 매도/하락 (파랑) |
| `--color-sell-bg` / `-border` | rgba 0.10 / 0.35 | rgba 0.07 / 0.30 | 매도 배지 배경·테두리 |
| `--color-strong` | `#f5a623` | (동일) | 강한 신호(★) |
| `--color-success` | `#22c55e` | (동일) | 성공·데몬 실행 |
| `--color-danger` | `#f04452` | (동일) | 위험·에러 |

### 레이아웃·기타 토큰

| 토큰 | 값 | 용도 |
|------|-----|------|
| `--font` | `-apple-system, 'Segoe UI', Pretendard, …` | 기본 폰트 |
| `--radius` / `--radius-md` | `6px` / `8px` | 모서리 |
| `--sidebar-width` | `184px` | 사이드바 폭 |
| `--topbar-height` | `46px` | 상단바 높이 |
| `--transition` | `0.15s ease` | 공통 트랜지션 |
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,.3)` | 약한 그림자 |

테마 토글: `<html data-theme="dark|light">`. 기본 다크. 저장은 `localStorage['signal-theme']`, FOUC 방지 스크립트가 `base.html` 최상단에 있다.

## 6. 검증 (변경 후 필수)

UI를 바꾼 뒤 다음을 돌려 깨짐을 확인한다.

```bash
python scripts/ui_check.py
```

검사 항목: (a) 템플릿이 쓰는 클래스가 CSS에 존재하는지, (b) CSS 클래스 중복 정의, (c) 토큰 밖 하드코딩 색상. 자세한 내용은 [`collaboration-prd.md`](collaboration-prd.md) §4 / §7-Q3.

추가 도구 (Phase 3):

```bash
python scripts/ui_snapshot.py contrast              # 토큰 대비비 표 (WCAG AA)
python scripts/ui_snapshot.py capture --tag before  # 스크린샷 캡처 (서버+playwright 필요)
python scripts/ui_snapshot.py diff before after     # 시각 회귀 비교
```

접근성·반응형 기준과 대비비 실측 결과: [`a11y-responsive.md`](a11y-responsive.md)

## 7. 작업 체크리스트

- [ ] 활성 폴더가 `signal-up`인지 확인 (다른 폴더는 참조/비활성)
- [ ] 색상은 `var(--token)`만 사용, 리터럴 금지
- [ ] 설정 폼 건드릴 때 `id`/`name`/`data-field`/`err-` 보존
- [ ] 새 필드는 `settings.js`의 `*_FIELDS` 집합에 등록
- [ ] 변경 후 `python scripts/ui_check.py` 통과
