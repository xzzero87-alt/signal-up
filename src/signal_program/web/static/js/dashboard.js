// dashboard.js — 30초 폴링 + 필터 + 카운트다운 (외부 프레임워크 없음)
'use strict';

const POLL_INTERVAL_MS = 30_000;
let lastUpdateAt = null;

async function fetchDashboard() {
  try {
    const res = await fetch('/api/dashboard');
    if (!res.ok) { showError('대시보드 정보를 가져오지 못했습니다 (' + res.status + ')'); return; }
    const data = await res.json();
    renderHeader(data);
    lastUpdateAt = Date.now();
    document.getElementById('error-msg').style.display = 'none';
  } catch (e) {
    showError('네트워크 오류: ' + e.message);
  }

  try {
    const params = buildFilterParams();
    const res2 = await fetch('/api/signals/recent?' + params);
    if (res2.ok) renderSignalTable(await res2.json());
  } catch (_) { /* ignore */ }
}

function buildFilterParams() {
  const p = new URLSearchParams({ limit: 50 });
  const market    = document.getElementById('filter-market')?.value;
  const direction = document.getElementById('filter-direction')?.value;
  const mode      = document.getElementById('filter-mode')?.value;
  const strength  = document.getElementById('filter-strength')?.value;
  if (market)    p.set('market', market);
  if (direction) p.set('direction', direction);
  if (mode)      p.set('mode', mode);
  if (strength)  p.set('strength', strength);
  return p.toString();
}

function renderHeader(data) {
  const el = document.getElementById('daemon-status-text');
  if (el) el.textContent = data.daemon_status === 'running' ? '실행 중' : '중지됨';
  const sigs = data.recent_signals || [];
  const lastEl = document.getElementById('last-signal-text');
  if (lastEl && sigs.length > 0) {
    const s = sigs[sigs.length - 1].signal || {};
    lastEl.textContent = (s.market || '—') + ' ' + (s.direction || '') + ' ' + (s.triggered_at || '').slice(0, 16);
  }
}

function renderSignalTable(signals) {
  const tbody = document.getElementById('signal-tbody');
  if (!tbody) return;
  if (!signals || signals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-row">시그널 없음</td></tr>';
    return;
  }
  tbody.innerHTML = [...signals].reverse().map(r => {
    const s = r.signal || {};
    const ind = s.indicators || {};
    const ts = (s.triggered_at || '').replace('T', ' ').slice(0, 16);
    const dir = s.direction === 'buy' ? '🟢 BUY' : '🔴 SELL';
    const str = s.strength === 'strong' ? '★★' : '★';
    return `<tr>
      <td>${ts}</td><td>${s.market||'—'}</td><td>${s.mode||'—'}</td>
      <td>${dir}</td><td>${str}</td>
      <td>${s.price ? s.price.toLocaleString('ko-KR') : '—'}</td>
      <td>${ind.bb_pct_b != null ? ind.bb_pct_b.toFixed(2) : '—'}</td>
      <td>${ind.cci != null ? ind.cci.toFixed(0) : '—'}</td>
      <td>${ind.volume_ratio != null ? ind.volume_ratio.toFixed(1) + '배' : '—'}</td>
    </tr>`;
  }).join('');
}

function applyFilters() { fetchDashboard(); }

function showError(msg) {
  const el = document.getElementById('error-msg');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function tickCountdown() {
  if (!lastUpdateAt) return;
  const el = document.getElementById('last-update');
  if (el) el.textContent = Math.floor((Date.now() - lastUpdateAt) / 1000) + '초 전';
}

fetchDashboard();
setInterval(fetchDashboard, POLL_INTERVAL_MS);
setInterval(tickCountdown, 1_000);
