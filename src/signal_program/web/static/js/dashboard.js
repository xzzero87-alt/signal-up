// dashboard.js — M18 테이블 뷰 (트레이딩 터미널 스타일)
// POLL_INTERVAL_MS, _MARKET_MODE 은 index.html 인라인 <script>에서 선언됨.
'use strict';

const MODE_LABEL = {
  BB_CCI: 'BB+CCI',
  FRACTAL: '프랙탈',
  // 레거시 키 (하위 호환)
  A: 'BB+CCI', B: 'B 스퀴즈', C: 'C 가중치', D: '프랙탈',
  E: 'Donchian', F: 'RSI2',  // 전략 확장 v2.3
};

let _lastUpdateAt = null;
let _dirFilter  = '';
let _strFilter  = false;
let _expandedId = null;      // 펼쳐진 행의 signal_id
let _knownIds   = null;      // 직전 폴링의 signal_id 집합 (새 신호 플래시용)

// ── 상대 시간 ────────────────────────────────────────────────────────────────

function relTime(iso) {
  if (!iso) return '—';
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 0 || isNaN(diff)) return '—';
  if (diff < 60) return '방금';
  if (diff < 3600) return Math.floor(diff / 60) + '분 전';
  if (diff < 86400) return Math.floor(diff / 3600) + '시간 전';
  return Math.floor(diff / 86400) + '일 전';
}

// ── 폴링 ────────────────────────────────────────────────────────────────────

async function fetchDashboard() {
  try {
    const res = await fetch('/api/dashboard');
    if (!res.ok) { showError('대시보드 정보를 가져오지 못했습니다 (' + res.status + ')'); return; }
    const data = await res.json();
    _renderDaemonStatus(data);
    document.getElementById('error-msg').style.display = 'none';
  } catch (e) {
    showError('네트워크 오류: ' + e.message);
  }

  if (typeof _MARKET_MODE !== 'undefined' && _MARKET_MODE === 'kr') return;

  try {
    const params = buildFilterParams();
    const res2 = await fetch('/api/signals/cards?' + params);
    if (res2.ok) {
      const records = await res2.json();
      renderTable(records, 'signal-tbody', 'signal-empty');
      updateCounters(records);
      _populateMarketOptions(records);
      document.getElementById('footer-last-scan').textContent = new Date().toLocaleTimeString('ko-KR');
    }
  } catch (_) { /* ignore */ }

  _lastUpdateAt = Date.now();
}

function buildFilterParams() {
  const p = new URLSearchParams({ limit: 100 });
  const market = document.getElementById('filter-market')?.value;
  const mode   = document.getElementById('filter-mode')?.value;
  if (market) p.set('market', market);
  if (mode)   p.set('mode', mode);
  if (_dirFilter) p.set('direction', _dirFilter);
  if (_strFilter) p.set('strength', 'strong');
  return p.toString();
}

// ── 테이블 렌더 ──────────────────────────────────────────────────────────────

function renderTable(records, tbodyId, emptyId) {
  const tbody = document.getElementById(tbodyId);
  const empty = document.getElementById(emptyId);
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!records || !records.length) {
    if (empty) empty.style.display = '';
    return;
  }
  if (empty) empty.style.display = 'none';

  const newIds = new Set();

  records.forEach(rec => {
    const sig   = rec.signal ?? rec;
    const dir   = (sig.direction ?? '').toLowerCase();
    const isBuy = dir === 'buy';
    const mode  = sig.mode ?? sig.strategy_mode ?? '';
    const chg   = sig.change_pct;
    const isKr  = !String(sig.market ?? '').startsWith('KRW-');
    const price = sig.price != null ? Number(sig.price).toLocaleString('ko-KR') + '원' : '—';
    const sigId = sig.signal_id ?? ((sig.triggered_at ?? '') + '_' + (sig.market ?? ''));
    newIds.add(sigId);

    let chgHtml;
    if (chg == null) {
      chgHtml = '<span class="chg-flat">—</span>';
    } else if (chg > 0) {
      chgHtml = `<span class="chg-up">+${chg.toFixed(2)}%</span>`;
    } else if (chg < 0) {
      chgHtml = `<span class="chg-down">${chg.toFixed(2)}%</span>`;
    } else {
      chgHtml = '<span class="chg-flat">0.00%</span>';
    }

    const marketHtml = isKr
      ? `${sig.market}<span class="market-sub">${sig.exchange ?? ''}</span>`
      : (sig.market ?? '—');

    const isStrong = String(sig.strength ?? '').toUpperCase() === 'STRONG';
    const isNew    = _knownIds !== null && !_knownIds.has(sigId);

    const tr = document.createElement('tr');
    tr.className = 'sig-row' + (isNew ? ' row-new' : '') + (_expandedId === sigId ? ' expanded' : '');
    tr.dataset.sigId = sigId;
    tr.innerHTML = `
      <td>${marketHtml}</td>
      <td><span class="${isBuy ? 'dir-buy' : 'dir-sell'}">${isBuy ? '▲ 매수' : '▼ 매도'}</span></td>
      <td><span class="strat-badge">${MODE_LABEL[mode] ?? mode}</span></td>
      <td class="r">${price}</td>
      <td class="r">${chgHtml}</td>
      <td class="r"><span class="${isStrong ? 'str-strong' : 'str-normal'}">${isStrong ? '★ STRONG' : 'NORMAL'}</span></td>
      <td class="r" style="color:var(--color-muted-2);font-size:11px" title="${sig.triggered_at ?? ''}">${relTime(sig.triggered_at)}</td>
    `;
    tr.addEventListener('click', () => toggleDetail(tr, sig));
    tbody.appendChild(tr);

    if (_expandedId === sigId) tbody.appendChild(buildDetailRow(sig));
  });

  _knownIds = newIds;
}

// ── 행 확장 디테일 ───────────────────────────────────────────────────────────

function toggleDetail(tr, sig) {
  const sigId = tr.dataset.sigId;
  const existing = tr.parentElement.querySelector('tr.sig-detail');
  if (existing) existing.remove();
  document.querySelectorAll('tr.sig-row.expanded').forEach(r => r.classList.remove('expanded'));

  if (_expandedId === sigId) { _expandedId = null; return; }
  _expandedId = sigId;
  tr.classList.add('expanded');
  tr.after(buildDetailRow(sig));
}

function buildDetailRow(sig) {
  const tr = document.createElement('tr');
  tr.className = 'sig-detail';
  const td = document.createElement('td');
  td.colSpan = 7;

  const fmt = (v, d = 2) => (v == null || isNaN(v)) ? '—' : Number(v).toFixed(d);
  const fb = sig.feedback ?? null;
  const chartHtml = sig.chart_url
    ? `<div class="sig-detail-chart"><img src="${sig.chart_url}" alt="BB+CCI 차트"
         onerror="this.parentElement.style.display='none'"></div>`
    : '';

  td.innerHTML = `
    <div class="sig-detail-inner">
      <div class="sig-ind-grid">
        <span class="sig-ind-label">BB %B</span><span class="sig-ind-val">${fmt(sig.bb_pct_b)}</span>
        <span class="sig-ind-label">CCI</span><span class="sig-ind-val">${fmt(sig.cci, 1)}</span>
        <span class="sig-ind-label">거래량 비율</span><span class="sig-ind-val">${fmt(sig.volume_ratio)}×</span>
        <span class="sig-ind-label">발생 시각</span><span class="sig-ind-val">${sig.triggered_at ? new Date(sig.triggered_at).toLocaleString('ko-KR') : '—'}</span>
      </div>
      ${chartHtml}
      <div class="sig-detail-actions">
        <span class="sig-fb-label">이 신호는 어땠나요?</span>
        <div class="sig-fb-group">
          <button class="sig-fb-btn${fb === 'helpful' ? ' active' : ''}" data-fb="helpful">👍 유용</button>
          <button class="sig-fb-btn${fb === 'confusing' ? ' active' : ''}" data-fb="confusing">🤔 애매</button>
          <button class="sig-fb-btn${fb === 'bad' ? ' active' : ''}" data-fb="bad">👎 거짓</button>
        </div>
      </div>
    </div>
  `;
  td.querySelectorAll('.sig-fb-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      submitFeedback(sig.signal_id, btn.dataset.fb, td);
    });
  });
  tr.appendChild(td);
  return tr;
}

async function submitFeedback(signalId, feedback, container) {
  if (!signalId) return;
  try {
    const res = await fetch(`/api/signals/${encodeURIComponent(signalId)}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    });
    if (res.ok) {
      container.querySelectorAll('.sig-fb-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.fb === feedback));
      fetchFeedbackStats();
    }
  } catch (_) { /* ignore */ }
}

// ── 거짓신호율 배지 ──────────────────────────────────────────────────────────

async function fetchFeedbackStats() {
  const el = document.getElementById('fb-rate-badge');
  if (!el) return;
  try {
    const res = await fetch('/api/signals/stats?window=30');
    if (!res.ok) return;
    const s = await res.json();
    if (!s.has_data) { el.style.display = 'none'; return; }
    el.style.display = '';
    el.textContent = `거짓신호율 ${s.bad_rate.toFixed(0)}% (최근 ${s.total_count}건)`;
    el.classList.toggle('warn', s.bad_rate >= 30);
  } catch (_) { /* ignore */ }
}

// ── 카운터 업데이트 ──────────────────────────────────────────────────────────

function updateCounters(records) {
  if (!records) return;
  const buy    = records.filter(r => (r.signal ?? r).direction?.toLowerCase() === 'buy').length;
  const sell   = records.length - buy;
  const strong = records.filter(r => (r.signal ?? r).strength === 'STRONG').length;

  ['sum-total','sb-total'].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=records.length; });
  ['sum-buy',  'sb-buy'  ].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=buy; });
  ['sum-sell', 'sb-sell' ].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=sell; });
  ['sum-strong','sb-strong'].forEach(id=> { const el=document.getElementById(id); if(el) el.textContent=strong; });

  const crypto = records.filter(r => String((r.signal??r).market??'').startsWith('KRW-')).length;
  const kr     = records.length - crypto;
  const bc = document.getElementById('sb-badge-crypto'); if(bc) bc.textContent = crypto || '—';
  const bk = document.getElementById('sb-badge-kr');     if(bk) bk.textContent = kr     || '—';
}

// ── 필터 핸들러 ──────────────────────────────────────────────────────────────

function setDirFilter(btn, dir) {
  _dirFilter = dir;
  document.querySelectorAll('.tb-tag[data-dir]').forEach(function(b){ b.classList.remove('on'); });
  if (btn) btn.classList.add('on');
  applyFilters();
}

function toggleStrFilter(btn) {
  _strFilter = !_strFilter;
  if (btn) btn.classList.toggle('on', _strFilter);
  applyFilters();
}

function applyFilters() { fetchDashboard(); }

// ── 데몬 상태 ────────────────────────────────────────────────────────────────

function _renderDaemonStatus(data) {
  const running = data.daemon_status === 'running';
  const dot  = document.getElementById('topbar-daemon-dot');
  const text = document.getElementById('topbar-daemon-text');
  const btn  = document.getElementById('nav-daemon-btn');
  if (dot)  dot.className = 'daemon-dot' + (running ? ' running' : '');
  if (text) text.textContent = running ? '실행 중' : '정지됨';
  if (btn)  { btn.textContent = running ? '정지' : '시작'; btn.disabled = false; }
}

async function toggleDaemon() {
  const btn = document.getElementById('nav-daemon-btn');
  const running = (btn && btn.textContent === '정지');
  if (btn) btn.disabled = true;
  try {
    const res = await fetch('/api/daemon/' + (running ? 'stop' : 'start'), { method: 'POST' });
    if (res.status === 409) {
      const d = await res.json();
      alert((d.detail && d.detail.message) || '상태 충돌');
    }
    fetchDashboard();
  } catch (_) {
    if (btn) btn.disabled = false;
  }
}

// ── 마켓 옵션 자동 채우기 ────────────────────────────────────────────────────

function _populateMarketOptions(records) {
  const sel = document.getElementById('filter-market');
  if (!sel || sel.dataset.populated) return;
  const markets = [...new Set(records.map(r => (r.signal ?? r).market).filter(Boolean))].sort();
  markets.forEach(function(m) {
    const opt = document.createElement('option');
    opt.value = m; opt.textContent = m;
    sel.appendChild(opt);
  });
  sel.dataset.populated = '1';
}

// ── 카운트다운 ───────────────────────────────────────────────────────────────

function _tickCountdown() {
  const el = document.getElementById('refresh-countdown');
  if (!el) return;
  if (!_lastUpdateAt) { el.textContent = Math.floor(POLL_INTERVAL_MS / 1000); return; }
  const elapsed   = Math.floor((Date.now() - _lastUpdateAt) / 1000);
  const remaining = Math.max(0, Math.floor(POLL_INTERVAL_MS / 1000) - elapsed);
  el.textContent  = remaining;
}

// ── 에러 표시 ────────────────────────────────────────────────────────────────

function showError(msg) {
  const el = document.getElementById('error-msg');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

// ── 초기화 ───────────────────────────────────────────────────────────────────

fetchDashboard();
fetchFeedbackStats();
setInterval(fetchDashboard, POLL_INTERVAL_MS);
setInterval(_tickCountdown, 1_000);
