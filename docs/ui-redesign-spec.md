# UI 재설계 구현 명세서 — 트레이딩 터미널 스타일

**확정일**: 2026-05-28  
**대상 마일스톤**: M18 (GUI 리디자인)  
**작업 범위**: 프론트엔드 전용 (백엔드 API 변경 최소화)

---

## 1. 디자인 결정 요약

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 테마 | 라이트 기본 (다크 토글) | 다크 기본 (라이트 토글 유지) |
| 네비게이션 | 상단 수평 nav | **왼쪽 사이드바** |
| 시그널 표시 | 카드 그리드 | **테이블 (행 기반)** |
| 코인/국장 전환 | 상단 탭 | **사이드바 마켓 선택** |
| 등락률 | 없음 | **추가 (change_pct 컬럼)** |
| 매수/매도 색상 | 매수=초록, 매도=빨강 | **매수=빨강(한국 관행), 매도=파랑** |
| Summary | 없음 | **상단 4칸 요약 스트립** |

---

## 2. 디자인 토큰

`app.css`의 `:root` 와 `[data-theme="dark"]` 블록을 아래로 교체한다.  
기존 라이트 토큰은 `[data-theme="light"]`로 이동, 다크가 기본값이 된다.

```css
/* ── 기본(다크) 토큰 ── */
:root {
  --color-bg:          #232f45;   /* 메인 배경 */
  --color-surface:     #1c2840;   /* 사이드바·상단바·헤더 */
  --color-surface-2:   #243350;   /* hover·인풋·카드 내부 */
  --color-border:      #2a3a54;   /* 기본 구분선 */
  --color-border-2:    #2e4060;   /* 강조 구분선·인풋 테두리 */
  --color-text:        #c8d4e2;
  --color-muted:       #6a8098;
  --color-muted-2:     #4a6280;
  --color-primary:     #6ab0ff;
  --color-nav:         #1c2840;

  /* 시그널 색상 (한국 관행: 매수=빨강, 매도=파랑) */
  --color-buy:         #e05252;
  --color-buy-bg:      #351515;
  --color-buy-border:  #552525;
  --color-sell:        #6ab0ff;
  --color-sell-bg:     #112240;
  --color-sell-border: #1e3e6a;

  --color-strong:      #e8a020;
  --color-success:     #2cb56a;
  --color-danger:      #e05252;

  --font: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
  --radius: 4px;
  --radius-md: 6px;
  --sidebar-width: 168px;
  --topbar-height: 42px;
}

/* ── 라이트 토글 시 오버라이드 ── */
[data-theme="light"] {
  --color-bg:        #f0f2f7;
  --color-surface:   #ffffff;
  --color-surface-2: #f5f7fb;
  --color-border:    #dde3ec;
  --color-border-2:  #c8d0de;
  --color-text:      #1c2939;
  --color-muted:     #5f7080;
  --color-muted-2:   #8a9ab0;
  --color-nav:       #ffffff;
  --color-buy-bg:    #fff0f0;
  --color-buy-border:#f5c0c0;
  --color-sell-bg:   #f0f6ff;
  --color-sell-border:#bdd5f5;
}
```

---

## 3. 전체 레이아웃 구조

```
┌─────────────────────────────────────────────────────┐
│  TOPBAR (42px) — 브랜드 / 데몬 상태 / 시각           │
├──────────┬──────────────────────────────────────────┤
│          │  SUMMARY STRIP (4칸)                     │
│          ├──────────────────────────────────────────┤
│ SIDEBAR  │  TOOLBAR (필터 / 태그 / 갱신 카운트)      │
│ (168px)  ├──────────────────────────────────────────┤
│          │  TABLE                                   │
│          │  (tbody — 세로 스크롤)                    │
│          ├──────────────────────────────────────────┤
│          │  FOOTER (32px)                           │
└──────────┴──────────────────────────────────────────┘
```

### 3-1. TOPBAR

```html
<!-- base.html의 <nav> 블록 전체 교체 -->
<header class="topbar">
  <span class="topbar-brand">SIGNAL</span>
  <div class="topbar-right">
    <span id="topbar-market-status" class="topbar-market-tag"></span>
    <div class="topbar-daemon">
      <span class="daemon-dot" id="topbar-daemon-dot"></span>
      <span id="topbar-daemon-text">데몬 확인 중</span>
    </div>
    <button class="btn-theme" id="btn-theme" onclick="toggleTheme()" aria-label="테마 전환">
      <span id="themeIcon">☀️</span>
    </button>
    <span class="topbar-clock" id="topbar-clock"></span>
  </div>
</header>
```

```css
.topbar {
  position: sticky; top: 0; z-index: 100;
  height: var(--topbar-height);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex; align-items: center;
  padding: 0 16px; gap: 0; flex-shrink: 0;
}
.topbar-brand { color: var(--color-primary); font-size: 14px; font-weight: 700; letter-spacing: .04em; margin-right: 24px; }
.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.topbar-market-tag { font-size: 11px; padding: 2px 8px; border-radius: 3px; background: var(--color-surface-2); color: var(--color-primary); border: 1px solid var(--color-border-2); }
.topbar-daemon { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--color-muted); }
.daemon-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--color-muted); flex-shrink: 0; }
.daemon-dot.running { background: var(--color-success); }
.topbar-clock { font-size: 11px; color: var(--color-muted-2); font-variant-numeric: tabular-nums; }
```

**JS — 시각 업데이트** (`base.html` 인라인):

```javascript
(function tickClock() {
  const el = document.getElementById('topbar-clock');
  if (el) el.textContent = new Date().toLocaleString('ko-KR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  setTimeout(tickClock, 1000);
})();
```

---

### 3-2. SIDEBAR

`base.html`의 `<main>` 래퍼를 `.app-body`로 감싸고, 사이드바를 주입한다.

```html
<div class="app-body">
  <aside class="sidebar">
    <div class="sb-group-label">마켓</div>
    <a href="/?market=crypto" class="sb-item {% if market=='crypto' %}on{% endif %}">
      <i class="ti ti-currency-bitcoin" aria-hidden="true"></i>코인
      <span class="sb-badge" id="sb-badge-crypto">—</span>
    </a>
    <a href="/?market=kr" class="sb-item {% if market=='kr' %}on{% endif %}">
      <i class="ti ti-building-bank" aria-hidden="true"></i>국장
      <span class="sb-badge" id="sb-badge-kr">—</span>
    </a>

    <div class="sb-divider"></div>
    <div class="sb-group-label">전략</div>
    <!-- 클릭 시 filter-mode 셀렉트와 연동 -->
    <div class="sb-item" data-strategy="">
      <i class="ti ti-list" aria-hidden="true"></i>전체
    </div>
    <div class="sb-item" data-strategy="A">
      <i class="ti ti-arrows-horizontal" aria-hidden="true"></i>A 평균회귀
    </div>
    <div class="sb-item" data-strategy="B">
      <i class="ti ti-bolt" aria-hidden="true"></i>B 스퀴즈
    </div>
    <div class="sb-item" data-strategy="C">
      <i class="ti ti-chart-bar" aria-hidden="true"></i>C 가중치
    </div>
    <div class="sb-item" data-strategy="D">
      <i class="ti ti-wave-saw-tool" aria-hidden="true"></i>D 프랙탈
    </div>

    <div class="sb-divider"></div>
    <div class="sb-group-label">오늘 현황</div>
    <div class="sb-stat-box">
      <div class="sb-stat-row"><span>전체</span><span id="sb-total" class="sb-stat-val">—</span></div>
      <div class="sb-stat-row"><span>매수</span><span id="sb-buy"   class="sb-stat-val" style="color:var(--color-buy)">—</span></div>
      <div class="sb-stat-row"><span>매도</span><span id="sb-sell"  class="sb-stat-val" style="color:var(--color-sell)">—</span></div>
      <div class="sb-stat-row"><span>STRONG</span><span id="sb-strong" class="sb-stat-val" style="color:var(--color-strong)">—</span></div>
    </div>

    <div class="sb-divider"></div>
    <div class="sb-group-label">메뉴</div>
    <a href="/backtest" class="sb-item {% if active=='backtest' %}on{% endif %}">
      <i class="ti ti-chart-line" aria-hidden="true"></i>백테스트
    </a>
    <a href="/settings" class="sb-item {% if active=='settings' %}on{% endif %}">
      <i class="ti ti-settings" aria-hidden="true"></i>설정
    </a>
    <a href="/failures" class="sb-item {% if active=='failures' %}on{% endif %}">
      <i class="ti ti-alert-triangle" aria-hidden="true"></i>알림 실패
    </a>
  </aside>

  <div class="main-area">
    {% block content %}{% endblock %}
  </div>
</div>
```

```css
.app-body { display: flex; flex: 1; overflow: hidden; }

.sidebar {
  width: var(--sidebar-width); flex-shrink: 0;
  background: var(--color-surface); border-right: 1px solid var(--color-border);
  display: flex; flex-direction: column; overflow-y: auto;
}
.sidebar::-webkit-scrollbar { width: 0; }

.sb-group-label {
  font-size: 10px; color: var(--color-muted-2);
  text-transform: uppercase; letter-spacing: .08em;
  padding: 10px 14px 4px;
}
.sb-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px; font-size: 12px; color: var(--color-muted);
  text-decoration: none; cursor: pointer;
  border-left: 2px solid transparent;
  transition: background .1s, color .1s;
}
.sb-item:hover { color: var(--color-text); background: var(--color-surface-2); }
.sb-item.on  { color: var(--color-text); background: var(--color-surface-2); border-left-color: var(--color-primary); }
.sb-item i   { font-size: 14px; flex-shrink: 0; }
.sb-badge    { margin-left: auto; background: var(--color-surface-2); color: var(--color-primary); font-size: 10px; padding: 1px 6px; border-radius: 10px; border: 1px solid var(--color-border-2); }
.sb-divider  { height: 1px; background: var(--color-border); margin: 6px 0; }

.sb-stat-box { margin: 6px 10px; background: var(--color-surface-2); border: 1px solid var(--color-border-2); border-radius: 6px; padding: 10px 12px; }
.sb-stat-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; font-size: 11px; color: var(--color-muted); }
.sb-stat-val { font-weight: 600; font-variant-numeric: tabular-nums; color: var(--color-text); }

.main-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
```

---

### 3-3. SUMMARY STRIP (대시보드 전용)

```html
<div class="summary-strip">
  <div class="sum-cell"><div class="sum-label">전체</div><div class="sum-val" id="sum-total">—</div></div>
  <div class="sum-cell"><div class="sum-label">매수</div><div class="sum-val" id="sum-buy"   style="color:var(--color-buy)">—</div></div>
  <div class="sum-cell"><div class="sum-label">매도</div><div class="sum-val" id="sum-sell"  style="color:var(--color-sell)">—</div></div>
  <div class="sum-cell"><div class="sum-label">STRONG</div><div class="sum-val" id="sum-strong" style="color:var(--color-strong)">—</div></div>
</div>
```

```css
.summary-strip {
  display: flex; flex-shrink: 0;
  border-bottom: 1px solid var(--color-border);
}
.sum-cell { flex: 1; padding: 10px 16px; border-right: 1px solid var(--color-border); }
.sum-cell:last-child { border-right: none; }
.sum-label { font-size: 10px; color: var(--color-muted-2); margin-bottom: 4px; text-transform: uppercase; letter-spacing: .05em; }
.sum-val   { font-size: 20px; font-weight: 700; color: var(--color-text); font-variant-numeric: tabular-nums; }
```

---

### 3-4. TOOLBAR

```html
<div class="toolbar">
  <select id="filter-market" class="tb-select" onchange="applyFilters()">
    <option value="">전체 마켓</option>
  </select>
  <select id="filter-mode" class="tb-select" onchange="applyFilters()">
    <option value="">전체 전략</option>
    <option value="A">A 평균회귀</option>
    <option value="B">B 스퀴즈</option>
    <option value="C">C 가중치</option>
    <option value="D">D 프랙탈</option>
  </select>
  <button class="tb-tag on"  data-dir=""     onclick="setDirFilter(this,'')">전체</button>
  <button class="tb-tag"     data-dir="buy"  onclick="setDirFilter(this,'buy')">매수</button>
  <button class="tb-tag"     data-dir="sell" onclick="setDirFilter(this,'sell')">매도</button>
  <button class="tb-tag"     data-str="strong" onclick="toggleStrFilter(this)">STRONG</button>
  <span class="tb-spacer"></span>
  <span class="tb-refresh"><i class="ti ti-refresh" aria-hidden="true"></i><span id="refresh-countdown">30</span>초 후 갱신</span>
</div>
```

```css
.toolbar {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px; flex-shrink: 0;
  background: var(--color-surface); border-bottom: 1px solid var(--color-border);
}
.tb-select {
  background: var(--color-surface-2); border: 1px solid var(--color-border-2);
  border-radius: var(--radius); color: var(--color-muted); padding: 4px 8px;
  font-size: 11px; outline: none; cursor: pointer;
}
.tb-tag {
  font-size: 11px; padding: 4px 10px; border-radius: var(--radius);
  border: 1px solid var(--color-border-2); background: var(--color-surface-2);
  color: var(--color-muted); cursor: pointer;
}
.tb-tag.on { background: var(--color-sell-bg); color: var(--color-primary); border-color: var(--color-sell-border); }
.tb-spacer { flex: 1; }
.tb-refresh { font-size: 11px; color: var(--color-muted-2); display: flex; align-items: center; gap: 5px; }
```

---

### 3-5. SIGNAL TABLE

**컬럼 정의**:

| # | key | 헤더 | 정렬 | 비고 |
|---|-----|------|------|------|
| 1 | `market` | 마켓 | 좌 | 코인=KRW-XXX, 국장=종목명+KOSPI/KOSDAQ 뱃지 |
| 2 | `direction` | 방향 | 좌 | `▲ 매수` 빨강 / `▼ 매도` 파랑 |
| 3 | `mode` | 전략 | 좌 | `A 평균회귀` `B 스퀴즈` `C 가중치` `D 프랙탈` |
| 4 | `price` | 현재가 | 우 | `toLocaleString()` + 원 |
| 5 | `change_pct` | 등락률 | 우 | `+3.42%` 빨강 / `-1.87%` 파랑 / `0.00%` dim |
| 6 | `strength` | 강도 | 우 | `★ STRONG` 앰버 / `NORMAL` dim |
| 7 | `triggered_at` | 시각 | 우 | `HH:MM:SS` |

```html
<div class="tbl-wrap">
  <table id="signal-table">
    <colgroup>
      <col style="width:16%"><col style="width:10%"><col style="width:13%">
      <col style="width:17%"><col style="width:11%"><col style="width:11%">
      <col style="width:11%">
    </colgroup>
    <thead>
      <tr>
        <th>마켓</th><th>방향</th><th>전략</th>
        <th class="r">현재가</th><th class="r">등락률</th>
        <th class="r">강도</th><th class="r">시각</th>
      </tr>
    </thead>
    <tbody id="signal-tbody">
      <!-- JS renderTable()로 채움 -->
    </tbody>
  </table>
  <div id="signal-empty" class="tbl-empty" style="display:none">
    시그널 없음 — 데몬 실행 후 시그널이 수신되면 여기에 표시됩니다.
  </div>
</div>
```

```css
.tbl-wrap { flex: 1; overflow-y: auto; }
.tbl-wrap::-webkit-scrollbar { width: 4px; }
.tbl-wrap::-webkit-scrollbar-thumb { background: var(--color-border-2); border-radius: 2px; }

table { width: 100%; border-collapse: collapse; table-layout: fixed; }
thead tr { background: var(--color-surface); position: sticky; top: 0; z-index: 2; }
th { padding: 7px 12px; color: var(--color-muted-2); font-weight: 400; font-size: 11px; border-bottom: 1px solid var(--color-border); text-align: left; }
th.r { text-align: right; }
td { padding: 8px 12px; border-bottom: 1px solid var(--color-border); font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
td.r { text-align: right; }
tr:hover td { background: var(--color-surface-2); }

/* 방향 뱃지 */
.dir-buy  { display:inline-block; background:var(--color-buy-bg);  color:var(--color-buy);  font-size:11px; font-weight:700; padding:2px 7px; border-radius:3px; border:1px solid var(--color-buy-border); }
.dir-sell { display:inline-block; background:var(--color-sell-bg); color:var(--color-sell); font-size:11px; font-weight:700; padding:2px 7px; border-radius:3px; border:1px solid var(--color-sell-border); }

/* 전략 뱃지 */
.strat-badge { font-size:10px; padding:2px 6px; border-radius:3px; background:var(--color-surface-2); color:var(--color-muted); border:1px solid var(--color-border-2); }

/* 등락률 */
.chg-up   { color: var(--color-buy);    font-weight: 500; }
.chg-down { color: var(--color-sell);   font-weight: 500; }
.chg-flat { color: var(--color-muted-2); }

/* 강도 */
.str-strong { color: var(--color-strong); font-weight: 600; }
.str-normal { color: var(--color-muted-2); }

/* 국장 서브 뱃지 */
.market-sub { font-size: 10px; color: var(--color-muted-2); margin-left: 4px; }

.tbl-empty { padding: 40px; text-align: center; color: var(--color-muted-2); font-size: 13px; }
```

**JS — `renderTable(records)` 구현** (`dashboard.js`에 추가):

```javascript
const MODE_LABEL = { A:'A 평균회귀', B:'B 스퀴즈', C:'C 가중치', D:'D 프랙탈' };

function renderTable(records) {
  const tbody = document.getElementById('signal-tbody');
  const empty = document.getElementById('signal-empty');
  tbody.innerHTML = '';

  if (!records.length) {
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  records.forEach(rec => {
    const sig = rec.signal ?? rec;
    const dir = (sig.direction ?? '').toLowerCase();
    const isBuy = dir === 'buy';
    const mode = sig.mode ?? sig.strategy_mode ?? '';
    const chg = sig.change_pct;               // float | null
    const isKr = !String(sig.market ?? '').startsWith('KRW-');
    const price = sig.price != null ? Number(sig.price).toLocaleString('ko-KR') + '원' : '—';
    const time  = sig.triggered_at ? new Date(sig.triggered_at).toLocaleTimeString('ko-KR') : '—';

    let chgHtml;
    if (chg == null) {
      chgHtml = '<span class="chg-flat">—</span>';
    } else if (chg > 0) {
      chgHtml = `<span class="chg-up">+${chg.toFixed(2)}%</span>`;
    } else if (chg < 0) {
      chgHtml = `<span class="chg-down">${chg.toFixed(2)}%</span>`;
    } else {
      chgHtml = `<span class="chg-flat">0.00%</span>`;
    }

    const marketHtml = isKr
      ? `${sig.market}<span class="market-sub">${sig.exchange ?? ''}</span>`
      : sig.market ?? '—';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${marketHtml}</td>
      <td><span class="${isBuy ? 'dir-buy' : 'dir-sell'}">${isBuy ? '▲ 매수' : '▼ 매도'}</span></td>
      <td><span class="strat-badge">${MODE_LABEL[mode] ?? mode}</span></td>
      <td class="r">${price}</td>
      <td class="r">${chgHtml}</td>
      <td class="r"><span class="${sig.strength === 'STRONG' ? 'str-strong' : 'str-normal'}">${sig.strength === 'STRONG' ? '★ STRONG' : 'NORMAL'}</span></td>
      <td class="r" style="color:var(--color-muted-2);font-size:11px">${time}</td>
    `;
    tbody.appendChild(tr);
  });
}
```

**Summary 및 Sidebar 카운터 업데이트** (`dashboard.js`):

```javascript
function updateCounters(records) {
  const buy    = records.filter(r => (r.signal ?? r).direction?.toLowerCase() === 'buy').length;
  const sell   = records.length - buy;
  const strong = records.filter(r => (r.signal ?? r).strength === 'STRONG').length;

  ['sum-total','sb-total'].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=records.length; });
  ['sum-buy',  'sb-buy'  ].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=buy; });
  ['sum-sell', 'sb-sell' ].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=sell; });
  ['sum-strong','sb-strong'].forEach(id=> { const el=document.getElementById(id); if(el) el.textContent=strong; });

  // 사이드바 뱃지 (코인/국장 구분)
  const crypto = records.filter(r => String((r.signal??r).market??'').startsWith('KRW-')).length;
  const kr     = records.length - crypto;
  const bc = document.getElementById('sb-badge-crypto'); if(bc) bc.textContent = crypto;
  const bk = document.getElementById('sb-badge-kr');     if(bk) bk.textContent = kr;
}
```

---

### 3-6. FOOTER

```html
<footer class="page-footer">
  <span class="footer-item"><i class="ti ti-database" aria-hidden="true"></i>signals.jsonl</span>
  <span class="footer-item"><i class="ti ti-clock" aria-hidden="true"></i>마지막 스캔: <span id="footer-last-scan">—</span></span>
  <span class="footer-item footer-right"><i class="ti ti-shield-check" aria-hidden="true"></i>참고용 시그널 · 자동매매 아님</span>
</footer>
```

```css
.page-footer {
  height: 32px; flex-shrink: 0;
  background: var(--color-surface); border-top: 1px solid var(--color-border);
  display: flex; align-items: center; gap: 16px; padding: 0 16px;
}
.footer-item { font-size: 11px; color: var(--color-muted-2); display: flex; align-items: center; gap: 5px; }
.footer-item i { font-size: 12px; }
.footer-right { margin-left: auto; }
```

---

## 4. 등락률(change_pct) 백엔드 추가

`Signal` 모델에 선택적 필드 추가 (DESIGN.md §8.3 불변 시그니처 준수 — 신규 optional 필드 허용).

### 4-1. `models.py`

```python
class Signal(BaseModel, frozen=True, extra="forbid"):
    # ... 기존 필드 그대로 유지 ...
    change_pct: float | None = None  # 시그널 발생 시점의 종가 등락률 (전봉 대비 %)
```

### 4-2. 각 전략 `evaluate()` 에서 계산

```python
# 공통 헬퍼 — strategies/base.py 또는 indicators/__init__.py
def calc_change_pct(candles: pd.DataFrame) -> float | None:
    """df.iloc[-1].close 기준 전봉 대비 등락률 (%)."""
    if len(candles) < 2:
        return None
    prev  = float(candles.iloc[-2]["close"])
    curr  = float(candles.iloc[-1]["close"])
    if prev == 0:
        return None
    return round((curr - prev) / prev * 100, 2)
```

Signal 생성 시 `change_pct=calc_change_pct(candles)` 로 전달.

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `web/templates/base.html` | **교체** | topbar + sidebar + app-body 구조로 전환 |
| `web/templates/index.html` | **교체** | summary-strip + toolbar + table + footer |
| `web/static/css/app.css` | **교체** | 디자인 토큰 전면 교체, 새 컴포넌트 CSS |
| `web/static/js/dashboard.js` | **수정** | `renderTable()`, `updateCounters()` 추가; 기존 `renderCards()` 제거 |
| `web/templates/settings.html` | **CSS만** | 기존 폼 로직 그대로, 사이드바 레이아웃에 맞게 `.main` 패딩 조정 |
| `web/templates/backtest.html` | **CSS만** | 동일 |
| `web/templates/failures.html` | **CSS만** | 동일 |
| `models.py` | **필드 추가** | `Signal.change_pct: float \| None = None` |
| `strategies/bb_cci.py` | **수정** | Signal 생성 시 `change_pct=calc_change_pct(candles)` 전달 |
| `strategies/kr_fractal.py` | **신규/수정** | 동일 |

---

## 6. 구현 순서 (Claude Code 권장)

```
1. models.py — change_pct 필드 추가 → mypy 통과 확인
2. strategies/ — calc_change_pct 헬퍼 + 각 전략에 전달
3. app.css — 디자인 토큰 전면 교체
4. base.html — topbar + sidebar + app-body
5. index.html — summary-strip + toolbar + table
6. dashboard.js — renderTable() + updateCounters() + 필터 로직
7. 나머지 페이지(settings, backtest, failures) — CSS 조정만
8. pytest --cov=src/ 통과 확인
9. uv run signal serve 로 브라우저 직접 확인
```

---

## 7. 변경 금지 사항 (하드라인 재확인)

- Signal / Candle / IndicatorSnapshot 기존 필드 수정 금지 (추가만 허용)
- 자동매매 코드 없음
- API 엔드포인트 URL 변경 금지 (`/api/dashboard`, `/api/kr/signals` 등)
- settings.js / backtest.js 로직 변경 금지 (CSS 조정만)
