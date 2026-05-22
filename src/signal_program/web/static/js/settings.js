// settings.js — 설정 저장 + 422 처리 + 토스트 (Vanilla JS)
'use strict';

// 시크릿/식별자 필드: 항상 string. Number 변환 금지
const STRING_FIELDS = new Set([
  'telegram_bot_token',
  'telegram_chat_id',
]);

// 정수 필드
const INT_FIELDS = new Set([
  'bb_period', 'cci_period', 'cci_threshold_normal', 'cci_threshold_strong',
  'squeeze_lookback', 'cooldown_hours',
  'sto_oversold', 'sto_overbought',          // V2 (ADR-0010)
]);

// 부동소수 필드
const FLOAT_FIELDS = new Set([
  'bb_std_mult', 'volume_ratio_min_a', 'volume_ratio_min_b', 'squeeze_quantile',
  'bb_weight', 'cci_weight', 'sto_weight', 'obv_weight', // V2 가중치
  'buy_threshold', 'sell_threshold',                      // V2 임계값
]);

async function saveSettings(event) {
  event.preventDefault();
  clearErrors();

  const form = document.getElementById('settings-form');
  const fd = new FormData(form);
  const body = {};

  for (const [key, val] of fd.entries()) {
    // whitelist_markets: 빈 입력도 backend에 명시적으로 전달 (검증은 backend v2.0.2가 담당)
    if (key === 'whitelist_markets') {
      body[key] = (val ?? '').split(',').map(v => v.trim()).filter(Boolean);
      continue;
    }
    if (val === '' || val == null) continue;
    if (key === 'dry_run') {
      body[key] = true;
    } else if (STRING_FIELDS.has(key)) {
      body[key] = val;
    } else if (INT_FIELDS.has(key)) {
      const n = parseInt(val, 10);
      body[key] = isNaN(n) ? val : n;
    } else if (FLOAT_FIELDS.has(key)) {
      const n = parseFloat(val);
      body[key] = isNaN(n) ? val : n;
    } else {
      body[key] = val;
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
    // radio 버튼 그룹 (strategy_version 등)
    const radios = document.querySelectorAll(`input[type="radio"][name="${key}"]`);
    if (radios.length > 0) {
      radios.forEach(r => { r.checked = (r.value === String(val)); });
      if (typeof updateV2Dim === 'function') updateV2Dim();
      continue;
    }
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
    // V2 기본값 (ADR-0010)
    strategy_version: 'v1',
    bb_weight: 0.20, cci_weight: 0.20, sto_weight: 0.20, obv_weight: 0.40,
    buy_threshold: 0.65, sell_threshold: 0.65,
    sto_oversold: 15, sto_overbought: 85,
  };
  for (const [key, val] of Object.entries(defaults)) {
    const radios = document.querySelectorAll(`input[type="radio"][name="${key}"]`);
    if (radios.length > 0) {
      radios.forEach(r => { r.checked = (r.value === String(val)); });
      continue;
    }
    const el = document.getElementById(key);
    if (!el) continue;
    if (el.type === 'checkbox') el.checked = !!val;
    else el.value = val;
  }
  if (typeof updateV2Dim === 'function') updateV2Dim();
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
  let matchedCount = 0;
  for (const { field, message } of errors) {
    // 안전망: 옛 응답 형식 호환 — "body.bb_period" → "bb_period"
    const fieldName = (field || '').replace(/^(body|query|path|header|cookie)\./, '');
    const el = document.getElementById('err-' + fieldName);
    if (el) { el.textContent = message; matchedCount++; }
    const input = document.getElementById(fieldName);
    if (input) input.style.borderColor = '#c62828';
  }
  // 매칭 0건 = silent failure 차단 — 글로벌 에러로 fallback
  if (matchedCount === 0 && errors.length > 0) {
    const summary = errors.map(e => `${(e.field || '').replace(/^[^.]+\./, '')}: ${e.message}`).join(' / ');
    showGlobalError('입력값을 확인하세요 — ' + summary);
  }
}

function clearErrors() {
  document.querySelectorAll('.field-error').forEach(el => { el.textContent = ''; });
  document.querySelectorAll('input').forEach(el => { el.style.borderColor = ''; });
  const ge = document.getElementById('form-errors');
  if (ge) ge.style.display = 'none';
}
