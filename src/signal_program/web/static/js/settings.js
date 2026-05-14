// settings.js — 설정 저장 + 422 처리 + 토스트 (Vanilla JS)
'use strict';

async function saveSettings(event) {
  event.preventDefault();
  clearErrors();

  const form = document.getElementById('settings-form');
  const fd = new FormData(form);
  const body = {};

  for (const [key, val] of fd.entries()) {
    if (val === '' || val == null) continue;
    if (key === 'whitelist_markets') {
      body[key] = val.split(',').map(v => v.trim()).filter(Boolean);
    } else if (key === 'dry_run') {
      body[key] = true;
    } else {
      const num = Number(val);
      body[key] = isNaN(num) ? val : num;
    }
  }
  if (!body.dry_run) body.dry_run = false;

  try {
    const res = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (res.ok) {
      showToast('설정이 저장되었습니다. 다음 폴링 사이클부터 반영됩니다.');
      refreshForm(await res.json());
      return;
    }

    if (res.status === 422) {
      const data = await res.json();
      const errors = Array.isArray(data.detail) ? data.detail : [];
      if (errors.length > 0) { showFieldErrors(errors); return; }
    }

    showGlobalError('서버 오류: ' + res.status);
  } catch (e) {
    showGlobalError('네트워크 오류: ' + e.message);
  }
}

function refreshForm(settings) {
  for (const [key, val] of Object.entries(settings)) {
    const el = document.getElementById(key);
    if (!el) continue;
    if (el.type === 'checkbox') el.checked = !!val;
    else if (key === 'whitelist_markets') el.value = Array.isArray(val) ? val.join(',') : val;
    else if (key !== 'telegram_bot_token') el.value = val;
  }
}

function resetToDefaults() {
  const defaults = {
    bb_period: 20, bb_std_mult: 2.0, cci_period: 20,
    cci_threshold_normal: 100, cci_threshold_strong: 200,
    volume_ratio_min_a: 1.0, volume_ratio_min_b: 1.5,
    squeeze_lookback: 120, squeeze_quantile: 0.20,
    cooldown_hours: 2, dry_run: false,
  };
  for (const [key, val] of Object.entries(defaults)) {
    const el = document.getElementById(key);
    if (!el) continue;
    if (el.type === 'checkbox') el.checked = !!val;
    else el.value = val;
  }
  showToast('기본값으로 초기화했습니다. 저장 버튼을 눌러 적용하세요.');
}

function showToast(msg) {
  const el = document.getElementById('save-toast');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 3000);
}

function showGlobalError(msg) {
  const el = document.getElementById('form-errors');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function showFieldErrors(errors) {
  for (const { field, message } of errors) {
    const el = document.getElementById('err-' + field);
    if (el) el.textContent = message;
    const input = document.getElementById(field);
    if (input) input.style.borderColor = '#c62828';
  }
}

function clearErrors() {
  document.querySelectorAll('.field-error').forEach(el => { el.textContent = ''; });
  document.querySelectorAll('input').forEach(el => { el.style.borderColor = ''; });
  const ge = document.getElementById('form-errors');
  if (ge) ge.style.display = 'none';
}
