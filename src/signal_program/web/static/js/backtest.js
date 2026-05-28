// backtest.js — 잡 제출 + 폴링(5초) + iframe 결과 표시 (Vanilla JS)
'use strict';

const JOBS_POLL_INTERVAL_MS = 5_000;

// 현재 활성 탭: 'coin' | 'kr'
let _btActiveTab = 'coin';

function switchBtTab(tab) {
  _btActiveTab = tab;
  document.getElementById('bt-coin-section').style.display = (tab === 'coin') ? '' : 'none';
  document.getElementById('bt-kr-section').style.display   = (tab === 'kr')   ? '' : 'none';
  document.getElementById('bt-tab-coin').classList.toggle('tab-active', tab === 'coin');
  document.getElementById('bt-tab-kr').classList.toggle('tab-active', tab === 'kr');
}

// 기본 날짜 설정 (최근 16개월)
(function initDates() {
  const to = new Date();
  const from = new Date(to);
  from.setMonth(from.getMonth() - 16);
  const fmt = d => d.toISOString().slice(0, 10);
  const pf = document.getElementById('period_from');
  const pt = document.getElementById('period_to');
  if (pf && !pf.value) pf.value = fmt(from);
  if (pt && !pt.value) pt.value = fmt(to);
})();

async function submitJob(isWalkforward) {
  clearErrors();
  // 활성 탭에 따라 마켓 선택
  const marketEl = (_btActiveTab === 'kr')
    ? document.getElementById('kr_market')
    : document.getElementById('market');
  const market = marketEl ? marketEl.value : '';
  if (!market) {
    showError('마켓/종목을 선택하세요.');
    return;
  }
  const period_from = document.getElementById('period_from').value;
  const period_to   = document.getElementById('period_to').value;
  const mode        = document.getElementById('mode').value;

  if (!period_from || !period_to) {
    showError('시작일과 종료일을 입력하세요.');
    return;
  }

  const body = { market, period_from, period_to, mode };

  if (isWalkforward) {
    body.kind = 'walkforward';
    const tm = document.getElementById('train_months');
    const vm = document.getElementById('validate_months');
    const gs = document.getElementById('grid_str');
    if (tm) body.train_months = parseInt(tm.value, 10);
    if (vm) body.validate_months = parseInt(vm.value, 10);
    if (gs && gs.value.trim()) body.grid_str = gs.value.trim();
  }

  try {
    const res = await fetch('/api/backtest/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (res.status === 429) {
      const data = await res.json();
      showToast((data.detail && data.detail.message) || '잡 큐가 가득 찼습니다.', 'warning');
      return;
    }
    if (res.status === 422) {
      const data = await res.json();
      const msgs = Array.isArray(data.detail)
        ? data.detail.map(e => (e.message || e.msg || JSON.stringify(e))).join(' / ')
        : JSON.stringify(data.detail);
      showError(msgs);
      return;
    }
    if (!res.ok) {
      showError('서버 오류: ' + res.status);
      return;
    }

    showToast('잡이 큐에 추가되었습니다.');
    refreshJobs();
  } catch (e) {
    showError('네트워크 오류: ' + e.message);
  }
}

async function refreshJobs() {
  try {
    const res = await fetch('/api/backtest/jobs?limit=20');
    if (!res.ok) return;
    const jobs = await res.json();
    renderJobsTable(jobs);
  } catch (_) { /* 무시 */ }
}

function renderJobsTable(jobs) {
  const tbody = document.getElementById('jobs-tbody');
  if (!tbody) return;
  if (!jobs || jobs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-row">잡 없음</td></tr>';
    return;
  }

  tbody.innerHTML = jobs.map(j => {
    const statusClass = {
      queued: 'job-queued', running: 'job-running',
      succeeded: 'job-succeeded', failed: 'job-failed',
    }[j.status] || '';
    const statusLabel = {
      queued: '대기', running: '실행 중', succeeded: '완료', failed: '실패',
    }[j.status] || j.status;

    const submitted = j.submitted_at ? new Date(j.submitted_at).toLocaleString('ko-KR') : '-';
    const elapsed = (j.started_at && j.finished_at)
      ? Math.round((new Date(j.finished_at) - new Date(j.started_at)) / 1000) + '초'
      : (j.started_at ? '실행 중' : '-');

    const resultBtn = (j.status === 'succeeded')
      ? `<button class="btn-sm" onclick="showResult('${j.job_id}')">보기</button>`
      : (j.status === 'failed' && j.error_message
          ? `<span title="${esc(j.error_message)}">오류</span>`
          : '-');

    return `<tr>
      <td>${submitted}</td>
      <td>${esc(j.kind)}</td>
      <td>${esc(j.market)}</td>
      <td>${esc(j.period_from)} ~ ${esc(j.period_to)}</td>
      <td class="${statusClass}">${statusLabel}</td>
      <td>${elapsed}</td>
      <td>${resultBtn}</td>
    </tr>`;
  }).join('');
}

function showResult(jobId) {
  const section = document.getElementById('result-section');
  const frame   = document.getElementById('result-frame');
  if (!section || !frame) return;
  frame.src = `/api/backtest/jobs/${jobId}/report`;
  section.style.display = '';
  section.scrollIntoView({ behavior: 'smooth' });
}

function showToast(msg, type) {
  const el = document.getElementById('save-toast');
  if (!el) return;
  el.textContent = msg;
  el.style.background = (type === 'warning') ? '#e65100' : '';
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 4000);
}

function showError(msg) {
  const el = document.getElementById('job-errors');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
}

function clearErrors() {
  const el = document.getElementById('job-errors');
  if (el) el.style.display = 'none';
}

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

refreshJobs();
setInterval(refreshJobs, JOBS_POLL_INTERVAL_MS);
