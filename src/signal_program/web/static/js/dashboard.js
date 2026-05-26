// dashboard.js — 30초 폴링 + 필터 + 카운트다운 (외부 프레임워크 없음)
'use strict';

// POLL_INTERVAL_MS 는 index.html 인라인 <script>에서 선언됨 (전역 상수)
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
  const running = data.daemon_status === 'running';
  const el = document.getElementById('daemon-status-text');
  if (el) el.textContent = running ? '실행 중' : '중지됨';

  // nav 데몬 토글 버튼 업데이트
  const statusEl = document.getElementById('nav-daemon-status');
  const btnEl = document.getElementById('nav-daemon-btn');
  if (statusEl) {
    statusEl.innerHTML = '데몬: <strong>' + (running ? '실행 중' : '정지됨') + '</strong>';
    statusEl.className = 'daemon-indicator ' + (running ? 'running' : 'stopped');
  }
  if (btnEl) {
    btnEl.textContent = running ? '정지' : '시작';
    btnEl.disabled = false;
  }

  const sigs = data.recent_signals || [];
  const lastEl = document.getElementById('last-signal-text');
  if (lastEl && sigs.length > 0) {
    const s = sigs[sigs.length - 1].signal || {};
    lastEl.textContent = (s.market || '—') + ' ' + (s.direction || '') + ' ' + (s.triggered_at || '').slice(0, 16);
  }
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
  } catch (e) {
    if (btn) btn.disabled = false;
  }
}

// ── R_P1_12: 거래량비 칩 ────────────────────────────────────────────────────
function _volChip(ratio) {
  if (ratio == null) return '<span class="chip chip-vol chip-vol--dim">—</span>';
  const val = ratio.toFixed(1) + '×';
  if (ratio >= 2.0) return `<span class="chip chip-vol chip-vol--high">${val}</span>`;
  if (ratio >= 1.5) return `<span class="chip chip-vol chip-vol--mid">${val}</span>`;
  return `<span class="chip chip-vol chip-vol--low">${val}</span>`;
}

// ── R_P1_11: 업비트 외부 링크 ───────────────────────────────────────────────
function _upbitLink(market) {
  if (!market) return '—';
  const url = 'https://upbit.com/exchange?code=CRIX.UPBIT.' + encodeURIComponent(market);
  return `${market}&nbsp;<a class="market-ext-link" href="${url}" target="_blank"
    rel="noopener noreferrer" aria-label="${market} 업비트에서 보기" title="업비트에서 보기">↗</a>`;
}

// ── R_P1_14: 쿨다운 칩 / 회고 버튼 ─────────────────────────────────────────
function _feedbackOrCooldown(status, safeMarket, safeTs, key) {
  if (status === 'cooled_down') {
    return '<span class="chip chip-cooldown" title="쿨다운 중 — 중복 알림 억제됨">⏸ 쿨다운</span>';
  }
  return `<button class="btn-feedback" data-key="${key}" data-label="👍"
      onclick="sendFeedback('${safeMarket}','${safeTs}','👍','${key}')"
      aria-label="${safeMarket} 좋음">👍</button>
    <button class="btn-feedback" data-key="${key}" data-label="👎"
      onclick="sendFeedback('${safeMarket}','${safeTs}','👎','${key}')"
      aria-label="${safeMarket} 나쁨">👎</button>`;
}

function renderSignalTable(signals) {
  const tbody = document.getElementById('signal-tbody');
  if (!tbody) return;
  if (!signals || signals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty-row">시그널 없음</td></tr>';
    return;
  }
  tbody.innerHTML = [...signals].reverse().map(r => {
    const s = r.signal || {};
    const ind = s.indicators || {};
    const status = r.status || 'ok';
    const ts = (s.triggered_at || '').replace('T', ' ').slice(0, 16);
    const dir = s.direction === 'buy' ? '🟢 BUY' : '🔴 SELL';
    const str = s.strength === 'strong' ? '★★' : '★';
    const modeLabel = s.mode === 'C' ? 'C(V2)' : (s.mode || '—');
    const key = (s.market || '') + '__' + (s.triggered_at || '').replace(/[^0-9]/g, '');
    const safeMarket = (s.market || '').replace(/'/g, '');
    const safeTs = (s.triggered_at || '').replace(/'/g, '');
    return `<tr>
      <td>${ts}</td>
      <td>${_upbitLink(s.market)}</td>
      <td>${modeLabel}</td>
      <td>${dir}</td><td>${str}</td>
      <td>${s.price ? s.price.toLocaleString('ko-KR') : '—'}</td>
      <td>${ind.bb_pct_b != null ? ind.bb_pct_b.toFixed(2) : '—'}</td>
      <td>${ind.cci != null ? ind.cci.toFixed(0) : '—'}</td>
      <td>${_volChip(ind.volume_ratio)}</td>
      <td>${_feedbackOrCooldown(status, safeMarket, safeTs, key)}</td>
    </tr>`;
  }).join('');
}

async function sendFeedback(market, triggeredAt, label, key) {
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ market, triggered_at: triggeredAt, label })
    });
    if (res.ok) {
      // 선택된 버튼 시각 표시
      document.querySelectorAll(`[data-key="${key}"]`).forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.label === label);
      });
    }
  } catch (_) { /* 네트워크 오류 무시 */ }
}

function applyFilters() { fetchDashboard(); }

function showError(msg) {
  const el = document.getElementById('error-msg');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

// ── R_P1_7: 다음 폴링까지 남은 시간 카운트다운 ──────────────────────────────
function tickCountdown() {
  const el = document.getElementById('last-update');
  if (!el) return;
  if (!lastUpdateAt) { el.textContent = '—'; return; }
  const elapsed = Math.floor((Date.now() - lastUpdateAt) / 1000);
  const remaining = Math.max(0, Math.floor(POLL_INTERVAL_MS / 1000) - elapsed);
  el.textContent = remaining > 0 ? remaining + '초 후' : '갱신 중...';
}

fetchDashboard();
setInterval(fetchDashboard, POLL_INTERVAL_MS);
setInterval(tickCountdown, 1_000);
