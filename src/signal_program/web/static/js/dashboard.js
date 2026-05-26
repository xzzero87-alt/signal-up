// dashboard.js — 30초 폴링 + 카드 뷰 렌더 (R_P1_9)
// 외부 프레임워크 없음. POLL_INTERVAL_MS 는 index.html 인라인 <script>에서 선언됨.
'use strict';

const CARDS_API = '/api/signals/cards';

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
    const res2 = await fetch(CARDS_API + '?' + params);
    if (res2.ok) renderSignalCards(await res2.json());
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

// ── 카드 렌더 (R_P1_9) ──────────────────────────────────────────────────────

function renderSignalCards(entries) {
  const container = document.getElementById('signal-cards');
  const empty = document.getElementById('signal-empty');
  if (!container) return;

  if (!entries || entries.length === 0) {
    if (empty) empty.style.display = '';
    container.querySelectorAll('.signal-card').forEach(el => el.remove());
    return;
  }

  if (empty) empty.style.display = 'none';

  const newIds = new Set(entries.map(e => e.signal_id));

  // 사라진 카드 제거
  container.querySelectorAll('.signal-card').forEach(el => {
    if (!newIds.has(el.dataset.signalId)) el.remove();
  });

  // 새 카드 prepend / 기존 카드 feedback 클래스 동기화
  entries.forEach(entry => {
    const existing = container.querySelector(`[data-signal-id="${CSS.escape(entry.signal_id)}"]`);
    if (existing) {
      existing.classList.toggle('feedback-bad', entry.feedback === 'bad');
      return;
    }
    container.insertBefore(buildSignalCard(entry), container.firstChild);
  });
}

/**
 * SignalCardEntry JSON → HTMLElement 변환 (R_P1_9).
 * @param {Object} entry - /api/signals/cards 응답 항목
 * @returns {HTMLElement}
 */
function buildSignalCard(entry) {
  const dirClass      = entry.direction === 'buy' ? 'direction-buy' : 'direction-sell';
  const strengthClass = entry.strength === 'strong' ? ' strength-strong' : '';
  const feedbackClass = entry.feedback === 'bad' ? ' feedback-bad' : '';
  const coin          = entry.market.replace('KRW-', '');
  const upbitUrl      = `https://upbit.com/exchange?code=CRIX.UPBIT.${entry.market}`;
  const time          = formatRelativeTime(entry.triggered_at);

  const volStrong  = entry.volume_ratio >= 2.0;
  const volClass   = volStrong ? ' strong' : '';

  const bbScore  = calcBbScore(entry.bb_pct_b, entry.direction);
  const cciScore = Math.min(Math.abs(entry.cci) / 200, 1.0);
  const scoreText = buildScoreSummary(entry);

  const modeTag = entry.mode === 'V2'
    ? '<span class="tag-v2">V2</span>'
    : '<span class="tag-v1">V1</span>';

  const dirChip = entry.direction === 'buy'
    ? '<span class="signal-direction direction-buy"><i class="ti ti-trending-up" aria-hidden="true"></i> 매수</span>'
    : '<span class="signal-direction direction-sell"><i class="ti ti-trending-down" aria-hidden="true"></i> 매도</span>';

  const fbHelpful   = entry.feedback === 'helpful'   ? ' selected helpful'   : '';
  const fbConfusing = entry.feedback === 'confusing'  ? ' selected confusing' : '';
  const fbBad       = entry.feedback === 'bad'        ? ' selected bad'       : '';

  // signal_id 는 onclick 인자에서 single-quote 이스케이프
  const sid = entry.signal_id.replace(/'/g, "\\'");

  const div = document.createElement('div');
  div.className = `signal-card ${dirClass}${strengthClass}${feedbackClass}`;
  div.dataset.signalId = entry.signal_id;
  div.innerHTML = `
    <div class="signal-meta">
      <div class="signal-market">
        <a href="${upbitUrl}" target="_blank" rel="noopener" class="market-link">
          ${coin} <i class="ti ti-external-link ext-icon" aria-hidden="true"></i>
        </a>
        ${dirChip}
        ${modeTag}
        <span class="vol-chip${volClass}">
          <i class="ti ti-activity" aria-hidden="true"></i>Vol ${entry.volume_ratio.toFixed(1)}x
        </span>
      </div>
      <div class="signal-time">${time}</div>
      <div class="signal-score">${scoreText}</div>
    </div>
    ${buildSparklineSvg(entry.sparkline_prices)}
    <div class="score-bars">
      ${buildScoreBar('BB', bbScore)}
      ${buildScoreBar('CCI', cciScore)}
      ${buildScoreBarNA('Sto', 'V1')}
      ${buildScoreBarNA('OBV', 'V1')}
    </div>
    <div class="feedback-buttons">
      <button type="button" class="fb-btn${fbHelpful}"
        onclick="submitFeedback(this,'${sid}','helpful')"
        title="도움됨" aria-label="이 시그널이 매매 결정에 도움이 됐음">👍</button>
      <button type="button" class="fb-btn${fbConfusing}"
        onclick="submitFeedback(this,'${sid}','confusing')"
        title="헷갈림" aria-label="이 시그널이 헷갈렸음">🤔</button>
      <button type="button" class="fb-btn${fbBad}"
        onclick="submitFeedback(this,'${sid}','bad')"
        title="거짓신호" aria-label="이 시그널은 거짓신호였음">👎</button>
    </div>
  `;
  return div;
}

// ── 회고 (R_P1_10) ───────────────────────────────────────────────────────────

async function submitFeedback(btn, signalId, value) {
  // optimistic UI 업데이트
  const buttons = btn.parentElement.querySelectorAll('.fb-btn');
  buttons.forEach(b => b.classList.remove('selected', 'helpful', 'confusing', 'bad'));
  btn.classList.add('selected', value);
  const card = btn.closest('.signal-card');
  if (card) card.classList.toggle('feedback-bad', value === 'bad');

  try {
    const resp = await fetch(`/api/signals/${encodeURIComponent(signalId)}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback: value }),
    });
    if (!resp.ok) {
      // eslint-disable-next-line no-console
      console.error('feedback 저장 실패:', await resp.text());
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('feedback 네트워크 오류:', err);
  }
}

// ── 헬퍼 함수 ────────────────────────────────────────────────────────────────

/** BB 강도 점수 0~1. 방향별로 band 이탈 정도를 정규화. */
function calcBbScore(bbPctB, direction) {
  if (direction === 'buy') {
    return Math.max(0, Math.min(1, 1 - bbPctB));
  }
  return Math.max(0, Math.min(1, bbPctB));
}

/** score-bar HTML 생성 */
function buildScoreBar(label, score) {
  const pct = Math.round(score * 100);
  const val = score.toFixed(2);
  return `
    <div class="score-row">
      <span class="label">${label}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <span class="value">${val}</span>
    </div>`;
}

/** N/A score-bar (V1 전용 지표) */
function buildScoreBarNA(label, naText) {
  return `
    <div class="score-row na">
      <span class="label">${label}</span>
      <div class="bar-track"></div>
      <span class="value">${naText}</span>
    </div>`;
}

/** score summary 텍스트 */
function buildScoreSummary(entry) {
  if (entry.direction === 'buy') {
    return `BB하단 + CCI ${Math.round(entry.cci)}`;
  }
  return `BB상단 + CCI +${Math.round(Math.abs(entry.cci))}`;
}

/**
 * SVG mini-chart sparkline.
 * prices: 최대 14개 float 배열, 없으면 회색 placeholder 반환.
 */
function buildSparklineSvg(prices) {
  if (!prices || prices.length < 2) {
    return `<svg class="mini-chart" viewBox="0 0 100 40" aria-hidden="true">
      <line x1="2" y1="20" x2="98" y2="20"
            stroke="rgba(128,128,128,0.3)" stroke-width="1" stroke-dasharray="3,3"/>
    </svg>`;
  }

  const N   = prices.length;
  const mid = Math.floor(N / 2);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const range = maxP - minP || 1;

  const toY = (p) => 3 + ((maxP - p) / range) * 34;
  const toX = (i) => 2 + (i / (N - 1)) * 96;

  const prePoints  = prices.slice(0, mid + 1).map((p, i) => `${toX(i)},${toY(p)}`).join(' ');
  const postPoints = prices.slice(mid).map((p, i) => `${toX(mid + i)},${toY(p)}`).join(' ');

  const midX = toX(mid);
  const midY = toY(prices[mid]);
  const isUp = prices[N - 1] > prices[mid];
  const lineColor   = isUp ? '#3b6d11' : '#a32d2d';
  const markerColor = '#a32d2d';

  const pctChange = ((prices[N - 1] - prices[mid]) / prices[mid] * 100).toFixed(2);
  const pctSign   = Number(pctChange) >= 0 ? '+' : '';
  const pctColor  = Number(pctChange) >= 0 ? '#3b6d11' : '#a32d2d';

  return `<svg class="mini-chart" viewBox="0 0 100 40" aria-hidden="true">
    <line x1="${midX}" y1="3" x2="${midX}" y2="37"
          stroke="rgba(128,128,128,0.35)" stroke-width="0.5" stroke-dasharray="2,2"/>
    <polyline fill="none" stroke="#888780" stroke-width="1.2" points="${prePoints}"/>
    <polyline fill="none" stroke="${lineColor}" stroke-width="1.5" points="${postPoints}"/>
    <circle cx="${midX}" cy="${midY}" r="2.5" fill="${markerColor}"/>
    <text x="${midX}" y="7" text-anchor="middle" font-size="9"
          fill="${markerColor}" font-weight="bold">▲</text>
    <text x="98" y="38" text-anchor="end" font-size="11" font-weight="700"
          fill="${pctColor}">${pctSign}${pctChange}%</text>
  </svg>`;
}

/** 상대 시간 포맷 (KST HH:MM + 경과시간) */
function formatRelativeTime(isoString) {
  const signalTime = new Date(isoString);
  const now        = new Date();
  const diffMs     = now - signalTime;
  const diffMin    = Math.floor(diffMs / 60000);

  const kstTime = signalTime.toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
  });

  if (diffMin < 1)  return `${kstTime} · 방금`;
  if (diffMin < 60) return `${kstTime} · ${diffMin}분 전`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24)   return `${kstTime} · ${diffH}시간 전`;
  return `${kstTime} · ${Math.floor(diffH / 24)}일 전`;
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
  const elapsed   = Math.floor((Date.now() - lastUpdateAt) / 1000);
  const remaining = Math.max(0, Math.floor(POLL_INTERVAL_MS / 1000) - elapsed);
  el.textContent  = remaining > 0 ? remaining + '초 후' : '갱신 중...';
}

fetchDashboard();
setInterval(fetchDashboard, POLL_INTERVAL_MS);
setInterval(tickCountdown, 1_000);
