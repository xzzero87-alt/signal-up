// settings.js — 설정 저장 + 422 처리 + 토스트 (Vanilla JS)
'use strict';

// 시크릿/식별자 필드: 항상 string. Number 변환 금지
const STRING_FIELDS = new Set([
  'telegram_bot_token',
  'telegram_chat_id',
  'kis_app_key',   // KIS (ADR-0016)
  'kis_app_secret',
]);

// 정수 필드
const INT_FIELDS = new Set([
  'bb_period', 'cci_period', 'cci_threshold_normal', 'cci_threshold_strong',
  'squeeze_lookback', 'cooldown_hours',
  'sto_oversold', 'sto_overbought',          // V2 (ADR-0010)
  'fractal_lookback', 'fractal_max_age', 'donchian_entry_period', 'donchian_exit_period', // 전략 확장 v2.3
  'rsi2_period', 'rsi2_trend_period',
  'kr_cooldown_hours_60m', 'kr_cooldown_hours_120m', // KIS (ADR-0016)
]);

// 체크박스 필드 집합 (미체크 시 false 명시 전달)
const CHECKBOX_FIELDS = new Set(['dry_run', 'kr_enabled', 'kis_is_paper']);

// 부동소수 필드
const FLOAT_FIELDS = new Set([
  'bb_std_mult', 'volume_ratio_min_a', 'volume_ratio_min_b', 'squeeze_quantile',
  'bb_weight', 'cci_weight', 'sto_weight', 'obv_weight', // V2 가중치
  'buy_threshold', 'sell_threshold',                      // V2 임계값
  'fractal_volume_threshold', 'fractal_volume_strong',   // 전략 확장 v2.3
  'donchian_volume_strong', 'rsi2_oversold', 'rsi2_overbought',
]);

async function saveSettings(event) {
  event.preventDefault();
  clearErrors();

  // 폼 스코프: 이벤트가 발생한 폼만 대상. 설정/시스템 페이지가 settings.js를 공유하며
  // 각자 가진 필드만 전송한다. PUT은 부분 업데이트(omit=변경 안 함)이므로 안전.
  const form = event.currentTarget || document.getElementById('settings-form');
  const fd = new FormData(form);
  const body = {};

  // 리스트 필드(종목설정): 해당 폼에 hidden input이 있을 때만 수집 → 빈 배열도 명시 전달.
  // settings_markets.js가 Set→hidden input을 mirror하므로 이것이 제출 진실.
  // 시스템 페이지처럼 종목 입력이 없는 폼은 omit → 워치리스트 보존(삭제 방지).
  for (const listField of ['whitelist_markets', 'kr_whitelist_symbols']) {
    if (form.querySelector(`[name="${listField}"]`)) {
      body[listField] = fd.getAll(listField).map(v => String(v).trim()).filter(Boolean);
    }
  }

  for (const [key, val] of fd.entries()) {
    if (key === 'whitelist_markets' || key === 'kr_whitelist_symbols') continue;
    if (val === '' || val == null) continue;
    if (CHECKBOX_FIELDS.has(key)) {
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
  // 체크박스: 이 폼에 실제로 존재하는 것만 명시적 boolean 전달.
  // (FormData는 미체크 체크박스를 누락하므로 직접 순회. 폼에 없는 필드는 omit → 변경 안 함.)
  // 폼 스코프이므로 다른 페이지의 체크박스를 false로 덮어쓰지 않는다.
  form.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    const key = cb.name || cb.id;
    if (key) body[key] = cb.checked;
  });

  try {
    const res = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (res.ok) {
      showToast('설정이 저장되었습니다. 다음 폴링 사이클부터 반영됩니다.');
      refreshForm(await res.json());
      // 변경 추적 바 리셋 (settings.html 인라인 리스너가 수신)
      document.dispatchEvent(new Event('settings-saved'));
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
    else if (key === 'whitelist_markets' || key === 'kr_whitelist_symbols')
      el.value = Array.isArray(val) ? val.join(',') : val;
    else if (key !== 'telegram_bot_token' && key !== 'kis_app_key_masked' && key !== 'kis_app_secret_masked')
      el.value = val;
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
    // 전략 확장 v2.3 기본값
    fractal_volume_threshold: 1.2, fractal_volume_strong: 2.0, fractal_max_age: 20,
    donchian_entry_period: 20, donchian_exit_period: 10, donchian_volume_strong: 1.5,
    rsi2_period: 2, rsi2_oversold: 10, rsi2_overbought: 90, rsi2_trend_period: 200,
    // KIS 기본값 (ADR-0016)
    kr_enabled: false, kis_is_paper: true,
    kr_cooldown_hours_60m: 2, kr_cooldown_hours_120m: 4,
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
