// settings_markets.js — 종목설정 멀티셀렉트 (코인/국장 탭) — v2.2 M3
// 설계 불변식(advisor): Set 이 단일 진실. 제출은 서버/JS가 mirror 하는 hidden input(name)만 담당.
// picker 행은 name 없는 순수 UI — 검색 필터·재렌더가 제출값에 영향 주지 않는다.
'use strict';

(function () {
  const TABS = {
    coin: {
      field: 'whitelist_markets',
      api: '/api/markets/coins',
      valKey: 'market',
      labelKey: 'korean_name',
      subKey: null,
    },
    kr: {
      field: 'kr_whitelist_symbols',
      api: '/api/markets/kr',
      valKey: 'code',
      labelKey: 'name',
      subKey: 'market', // KOSPI/KOSDAQ 뱃지
    },
  };

  // tabKey -> { set, initial, listEl, rows: [{val, search, el}] }
  const state = {};

  function $(id) {
    return document.getElementById(id);
  }

  function fireFormInput() {
    const form = $('settings-form');
    if (form) form.dispatchEvent(new Event('input', { bubbles: true }));
  }

  // ── hidden input mirror (제출 진실) ──
  function mirrorHidden(tabKey) {
    const cfg = TABS[tabKey];
    const box = $('hidden-' + cfg.field);
    if (!box) return;
    box.innerHTML = '';
    state[tabKey].set.forEach(function (val) {
      const inp = document.createElement('input');
      inp.type = 'hidden';
      inp.name = cfg.field;
      inp.value = val;
      box.appendChild(inp);
    });
  }

  function renderCount(tabKey) {
    const el = $(tabKey + '-count');
    if (el) el.textContent = String(state[tabKey].set.size);
  }

  // ── 선택 칩 (선택의 보편적 표현 — 유니버스 밖 항목도 표시) ──
  function renderChips(tabKey) {
    const box = $(tabKey + '-chips');
    if (!box) return;
    box.innerHTML = '';
    const set = state[tabKey].set;
    if (set.size === 0) {
      const empty = document.createElement('span');
      empty.className = 'ms-chips-empty';
      empty.textContent = '선택된 종목 없음';
      box.appendChild(empty);
      return;
    }
    set.forEach(function (val) {
      const chip = document.createElement('span');
      chip.className = 'ms-chip';
      const lbl = document.createElement('span');
      lbl.textContent = val;
      const x = document.createElement('button');
      x.type = 'button';
      x.className = 'ms-chip-x';
      x.textContent = '×';
      x.setAttribute('aria-label', val + ' 제거');
      x.addEventListener('click', function () {
        removeItem(tabKey, val);
      });
      chip.appendChild(lbl);
      chip.appendChild(x);
      box.appendChild(chip);
    });
  }

  function syncRowCheckbox(tabKey, val) {
    const listEl = state[tabKey].listEl;
    if (!listEl || !window.CSS || !CSS.escape) return;
    const cb = listEl.querySelector('input[data-val="' + CSS.escape(val) + '"]');
    if (cb) cb.checked = state[tabKey].set.has(val);
  }

  function toggleItem(tabKey, val) {
    const set = state[tabKey].set;
    if (set.has(val)) set.delete(val);
    else set.add(val);
    mirrorHidden(tabKey);
    renderChips(tabKey);
    renderCount(tabKey);
    syncRowCheckbox(tabKey, val);
    fireFormInput();
  }

  function removeItem(tabKey, val) {
    state[tabKey].set.delete(val);
    mirrorHidden(tabKey);
    renderChips(tabKey);
    renderCount(tabKey);
    syncRowCheckbox(tabKey, val);
    fireFormInput();
  }

  // ── picker 행 렌더 (1회) ──
  function renderList(tabKey, items) {
    const cfg = TABS[tabKey];
    const listEl = state[tabKey].listEl;
    if (!listEl) return;
    listEl.innerHTML = '';
    listEl.removeAttribute('data-loading');
    state[tabKey].rows = [];

    if (!items.length) {
      listEl.innerHTML = '<div class="ms-list-msg">목록이 비어 있습니다.</div>';
      return;
    }

    const frag = document.createDocumentFragment();
    items.forEach(function (item) {
      const val = item[cfg.valKey];
      const label = item[cfg.labelKey] || '';
      const sub = cfg.subKey ? item[cfg.subKey] || '' : '';

      const row = document.createElement('label');
      row.className = 'ms-item';

      const cb = document.createElement('input');
      cb.type = 'checkbox'; // name 없음 — 순수 UI
      cb.className = 'ms-cb';
      cb.setAttribute('data-val', val);
      cb.checked = state[tabKey].set.has(val);
      cb.addEventListener('change', function () {
        toggleItem(tabKey, val);
      });

      const code = document.createElement('span');
      code.className = 'ms-code';
      code.textContent = val;

      const name = document.createElement('span');
      name.className = 'ms-name';
      name.textContent = label;

      row.appendChild(cb);
      row.appendChild(code);
      row.appendChild(name);
      if (sub) {
        const badge = document.createElement('span');
        badge.className = 'ms-badge';
        badge.textContent = sub;
        row.appendChild(badge);
      }
      frag.appendChild(row);

      state[tabKey].rows.push({
        val: val,
        search: (val + ' ' + label).toLowerCase(),
        el: row,
      });
    });
    listEl.appendChild(frag);
  }

  // ── 검색: picker 가시성만 토글 (제출값 불변) ──
  function filterList(tabKey, query) {
    const q = (query || '').trim().toLowerCase();
    state[tabKey].rows.forEach(function (r) {
      r.el.style.display = !q || r.search.indexOf(q) !== -1 ? '' : 'none';
    });
  }

  function switchTab(tabKey) {
    ['coin', 'kr'].forEach(function (t) {
      const panel = $('ms-panel-' + t);
      if (panel) panel.style.display = t === tabKey ? '' : 'none';
      const tab = document.querySelector('.ms-tab[data-tab="' + t + '"]');
      if (tab) tab.classList.toggle('on', t === tabKey);
    });
  }

  async function loadTab(tabKey) {
    const cfg = TABS[tabKey];
    try {
      const res = await fetch(cfg.api);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const items = await res.json();
      renderList(tabKey, items);
    } catch (e) {
      // 로드 실패해도 hidden input(서버 시드)은 그대로 제출됨 — 데이터 손실 없음.
      const listEl = state[tabKey].listEl;
      if (listEl) {
        listEl.removeAttribute('data-loading');
        listEl.innerHTML =
          '<div class="ms-list-msg ms-list-err">목록을 불러오지 못했습니다. ' +
          '기존 선택은 유지됩니다.</div>';
      }
    }
  }

  // 변경 추적: 저장바(settings.html 인라인)가 호출
  window.getMarketsChanges = function () {
    const out = [];
    ['coin', 'kr'].forEach(function (t) {
      const st = state[t];
      if (!st) return;
      const changed =
        st.set.size !== st.initial.size ||
        Array.prototype.some.call(st.set, function (v) {
          return !st.initial.has(v);
        });
      if (changed) {
        out.push({
          key: TABS[t].field,
          label: t === 'coin' ? '코인 종목' : '국장 종목',
          from: st.initial.size + '종',
          to: st.set.size + '종',
        });
      }
    });
    return out;
  };

  // 저장 성공 시 기준값 갱신
  window.marketsCommit = function () {
    ['coin', 'kr'].forEach(function (t) {
      if (state[t]) state[t].initial = new Set(state[t].set);
    });
  };

  // 탭 전환 노출 (settings.html onclick)
  window.msSwitchTab = switchTab;

  function init() {
    const seedEl = $('markets-seed');
    let seed = { coin: [], kr: [] };
    if (seedEl) {
      try {
        seed = JSON.parse(seedEl.textContent);
      } catch (e) {
        seed = { coin: [], kr: [] };
      }
    }

    ['coin', 'kr'].forEach(function (t) {
      const initial = Array.isArray(seed[t]) ? seed[t] : [];
      state[t] = {
        set: new Set(initial),
        initial: new Set(initial),
        listEl: $(t + '-list'),
        rows: [],
      };
      mirrorHidden(t);
      renderChips(t);
      renderCount(t);

      const search = $(t + '-search');
      if (search) {
        search.addEventListener('input', function () {
          filterList(t, search.value);
        });
      }
    });

    switchTab('coin');
    loadTab('coin');
    loadTab('kr');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
