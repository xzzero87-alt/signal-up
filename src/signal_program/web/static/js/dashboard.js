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

let _daemonRunning = false;

async function fetchDashboard() {
  try {
    const res = await fetch('/api/dashboard');
    if (!res.ok) { showError('대시보드 정보를 가져오지 못했습니다 (' + res.status + ')'); return; }
    const data = await res.json();
    _daemonRunning = data.daemon_status === 'running';
    _renderDaemonStatus(data);
    const wl = (data.settings_summary ?? {}).whitelist_markets;
    _renderEmptyState(_daemonRunning, Array.isArray(wl) ? wl.length : null);
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

  _setText('sum-total', records.length);
  _setText('sum-buy', buy);
  _setText('sum-sell', sell);
  _setText('sum-strong', strong);
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
  _renderStatusPanel(data, running);
}

// ── 시스템 상태 패널 (M20) ──────────────────────────────────────────────────

const STRATEGY_LABEL = {
  v1: 'V1 · BB+CCI', v2: 'V2 · 4지표',
  v3: 'V3 · 프랙탈', v4: 'V4 · Donchian', v5: 'V5 · RSI(2)',
};

function _setText(id, txt) {
  const el = document.getElementById(id);
  if (el) el.textContent = txt;
}

function _renderStatusPanel(data, running) {
  const s = data.settings_summary ?? {};

  // 데몬 카드
  const dDot = document.getElementById('st-daemon-dot');
  if (dDot) dDot.className = 'st-dot ' + (running ? 'ok' : 'off');
  _setText('st-daemon-text', running ? '실행 중' : '정지됨');
  const startedAt = s.daemon_started_at;
  const lastSig   = s.last_signal_at;
  let dSub = running && startedAt ? '가동 ' + relTime(startedAt).replace(' 전', '째') : '시작 버튼으로 가동';
  if (lastSig) dSub += ' · 마지막 신호 ' + relTime(lastSig);
  _setText('st-daemon-sub', dSub);

  // 운용 현황 목록: 어떤 마켓 그룹이 어떤 전략으로 실행 중인지
  _renderRunList(s);

  // 알림 카드
  _renderNotifyCard(s);
}

const KR_STRATEGY_LABEL = { fractal: '프랙탈', bb_cci: 'BB+CCI' };

function _esc(t) {
  const d = document.createElement('span');
  d.textContent = String(t);
  return d.innerHTML;
}

function _renderRunList(s) {
  const box = document.getElementById('st-run-list');
  if (!box) return;
  const rows = [];

  // 코인 행
  const ver = String(s.strategy_version ?? 'v1');
  const markets = Array.isArray(s.whitelist_markets) ? s.whitelist_markets : [];
  const mPreview = markets.slice(0, 4).map(m => String(m).replace('KRW-', '')).join(', ')
    + (markets.length > 4 ? ' 외 ' + (markets.length - 4) + '개' : '');
  const coinParts = [];
  if (s.bb_period != null && s.bb_std_mult != null) coinParts.push('BB ' + s.bb_period + '/' + s.bb_std_mult);
  if (s.cci_threshold_normal != null) coinParts.push('CCI ±' + s.cci_threshold_normal);
  if (s.cooldown_hours != null) coinParts.push('쿨다운 ' + s.cooldown_hours + 'h');
  const coinDetail = markets.length
    ? '<span class="run-detail">' + _esc(markets.length + '개 마켓 (' + mPreview + ') · ' + coinParts.join(' · ')) + '</span>'
    : '<a class="run-warn" href="/settings">⚠ 감시 마켓 없음 — 설정에서 화이트리스트를 채워야 신호가 발생합니다 →</a>';
  rows.push(
    '<div class="run-row">' +
      '<span class="run-scope">코인</span>' +
      '<span class="run-strat">' + _esc(STRATEGY_LABEL[ver] ?? ver.toUpperCase()) + '</span>' +
      coinDetail +
    '</div>'
  );

  // 국장 행
  if (s.kr_enabled) {
    const krStrat = KR_STRATEGY_LABEL[String(s.kr_strategy)] ?? String(s.kr_strategy ?? '');
    const syms = Array.isArray(s.kr_whitelist_symbols) ? s.kr_whitelist_symbols : [];
    const sPreview = syms.slice(0, 4).join(', ') + (syms.length > 4 ? ' 외 ' + (syms.length - 4) + '개' : '');
    rows.push(
      '<div class="run-row">' +
        '<span class="run-scope">국장</span>' +
        '<span class="run-strat">' + _esc(krStrat) + '</span>' +
        '<span class="run-detail">' + _esc(syms.length + '개 종목 (' + (sPreview || '없음') + ')') + '</span>' +
      '</div>'
    );
  } else {
    rows.push('<div class="run-row"><span class="run-scope">국장</span><span class="run-off">비활성</span></div>');
  }

  // dry-run 경고
  if (s.dry_run) {
    rows.push('<div class="run-row"><span class="run-off">⚠ dry-run 켜짐 — 신호는 기록되지만 텔레그램 발송 안 함</span></div>');
  }

  box.innerHTML = rows.join('');
}

async function _renderNotifyCard(s) {
  const nDot = document.getElementById('st-notify-dot');
  if (s.dry_run) {
    if (nDot) nDot.className = 'st-dot';
    _setText('st-notify-text', 'dry-run');
    _setText('st-notify-sub', '신호는 기록되지만 텔레그램 발송 안 함');
    return;
  }
  try {
    const res = await fetch('/api/notifications/failures?limit=5');
    if (!res.ok) return;
    const fails = await res.json();
    const recent = fails.filter(f => (Date.now() - new Date(f.failed_at).getTime()) < 86400000);
    if (nDot) nDot.className = 'st-dot ' + (recent.length ? 'off' : 'ok');
    _setText('st-notify-text', recent.length ? ('실패 ' + recent.length + '건') : '텔레그램 정상');
    _setText('st-notify-sub', recent.length ? '최근 24시간 — 실패 이력에서 확인' : '최근 24시간 실패 없음');
  } catch (_) { /* ignore */ }
}

function _renderEmptyState(running, whitelistCount) {
  const title = document.getElementById('empty-title');
  const body  = document.getElementById('empty-body');
  if (!title || !body) return;
  if (whitelistCount === 0) {
    title.textContent = '감시할 마켓이 없습니다';
    body.textContent = '화이트리스트가 비어 있어 데몬이 돌아도 신호가 발생하지 않습니다. ' +
      '설정 → ② 운영에서 감시 마켓을 추가하세요 (예: KRW-BTC,KRW-ETH).';
  } else if (!running) {
    title.textContent = '데몬이 정지돼 있습니다';
    body.textContent = '상단 [시작] 버튼을 누르면 1시간봉 마감마다 화이트리스트 마켓을 평가합니다.';
  } else {
    title.textContent = '아직 신호가 없습니다 — 시스템은 정상 작동 중';
    body.textContent = '마감 봉마다 평가 중이지만 현재 전략 조건을 충족한 마켓이 없습니다. ' +
      '신호 빈도를 높이려면 설정에서 임계값(CCI·거래량 비율)을 낮춰보세요.';
  }
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
    ? '<div class="sig-detail-chart"><img src="' + sig.chart_url + '" alt="BB+CCI 차트" onerror="this.parentElement.style.display=\'none\'"></div>'
    : '';

  td.innerHTML =
    '<div class="sig-detail-inner">' +
      '<div class="sig-ind-grid">' +
        '<span class="sig-ind-label">BB %B</span><span class="sig-ind-val">' + fmt(sig.bb_pct_b) + '</span>' +
        '<span class="sig-ind-label">CCI</span><span class="sig-ind-val">' + fmt(sig.cci, 1) + '</span>' +
        '<span class="sig-ind-label">거래량 비율</span><span class="sig-ind-val">' + fmt(sig.volume_ratio) + '×</span>' +
        '<span class="sig-ind-label">발생 시각</span><span class="sig-ind-val">' + (sig.triggered_at ? new Date(sig.triggered_at).toLocaleString('ko-KR') : '—') + '</span>' +
      '</div>' +
      chartHtml +
      '<div class="sig-detail-actions">' +
        '<span class="sig-fb-label">이 신호는 어땠나요?</span>' +
        '<div class="sig-fb-group">' +
          '<button class="sig-fb-btn' + (fb === 'helpful' ? ' active' : '') + '" data-fb="helpful">👍 유용</button>' +
          '<button class="sig-fb-btn' + (fb === 'confusing' ? ' active' : '') + '" data-fb="confusing">🤔 애매</button>' +
          '<button class="sig-fb-btn' + (fb === 'bad' ? ' active' : '') + '" data-fb="bad">👎 거짓</button>' +
        '</div>' +
      '</div>' +
    '</div>';
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
    const res = await fetch('/api/signals/' + encodeURIComponent(signalId) + '/feedback', {
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
    el.textContent = '거짓신호율 ' + s.bad_rate.toFixed(0) + '% (최근 ' + s.total_count + '건)';
    el.classList.toggle('warn', s.bad_rate >= 30);
  } catch (_) { /* ignore */ }
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
  const total = Math.floor(POLL_INTERVAL_MS / 1000);
  let remaining = total;
  if (_lastUpdateAt) {
    const elapsed = Math.floor((Date.now() - _lastUpdateAt) / 1000);
    remaining = Math.max(0, total - elapsed);
  }
  const el = document.getElementById('refresh-countdown');
  if (el) el.textContent = remaining;
  _setText('st-next', remaining + '초 후');
  const bar = document.getElementById('st-progress-bar');
  if (bar) bar.style.width = Math.round(((total - remaining) / total) * 100) + '%';
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
