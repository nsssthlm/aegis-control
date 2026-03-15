/**
 * AEGIS CONTROL — Environment Selector Plugin
 * Dropdown to select environment: CEDERVALL / VALVX / GWSK / PERSONAL / ALL
 * Filters all panels and announces via herald-voice.
 */
(function() {
  'use strict';

  const ENVIRONMENTS = ['ALL', 'CEDERVALL', 'VALVX', 'GWSK', 'PERSONAL'];
  const STORAGE_KEY = 'aegis-env';
  const HERALD_URL = '/api/herald/speak'; // proxied or direct

  let currentEnv = localStorage.getItem(STORAGE_KEY) || 'ALL';

  // ── Build UI ──
  const container = document.getElementById('header-env');
  if (!container) return;

  const style = document.createElement('style');
  style.textContent = `
    .env-selector {
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .env-selector-label {
      font-size: 10px;
      color: var(--aegis-muted);
      letter-spacing: 2px;
      text-transform: uppercase;
    }
    .env-selector select {
      background: var(--aegis-bg);
      border: 1px solid var(--aegis-border);
      color: var(--aegis-primary);
      font-family: var(--aegis-font);
      font-size: 11px;
      font-weight: 700;
      padding: 3px 24px 3px 8px;
      letter-spacing: 2px;
      cursor: pointer;
      appearance: none;
      -webkit-appearance: none;
      outline: none;
      transition: border-color 0.2s;
    }
    .env-selector select:hover,
    .env-selector select:focus {
      border-color: var(--aegis-dim);
      box-shadow: 0 0 8px rgba(0, 255, 136, 0.15);
    }
    .env-selector-arrow {
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      pointer-events: none;
      color: var(--aegis-dim);
      font-size: 8px;
    }
  `;
  document.head.appendChild(style);

  container.innerHTML = `
    <div class="env-selector">
      <span class="env-selector-label">ENV</span>
      <select id="env-select">
        ${ENVIRONMENTS.map(env =>
          `<option value="${env}" ${env === currentEnv ? 'selected' : ''}>${env}</option>`
        ).join('')}
      </select>
      <span class="env-selector-arrow">&#9660;</span>
    </div>
  `;

  const select = document.getElementById('env-select');

  select.addEventListener('change', function() {
    const newEnv = this.value;
    const oldEnv = currentEnv;
    currentEnv = newEnv;

    // Save to localStorage
    localStorage.setItem(STORAGE_KEY, newEnv);

    // Dispatch env change event
    window.dispatchEvent(new CustomEvent('aegis:env-change', {
      detail: { env: newEnv, previousEnv: oldEnv }
    }));

    // Announce via herald-voice
    announceEnvChange(newEnv);

    console.log(`[AEGIS] Environment changed: ${oldEnv} -> ${newEnv}`);
  });

  // ── Announce via herald-voice ──
  function announceEnvChange(env) {
    const text = env === 'ALL'
      ? 'Switching to all environments view'
      : `Switching to ${env.toLowerCase()} environment`;

    fetch(HERALD_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, priority: 'low' })
    }).catch(() => {
      // Herald voice may not be available — silent fail
    });
  }

  // ── Public API ──
  window.aegisGetEnv = function() {
    return currentEnv;
  };

  window.aegisSetEnv = function(env) {
    if (ENVIRONMENTS.includes(env)) {
      select.value = env;
      select.dispatchEvent(new Event('change'));
    }
  };

  // Dispatch initial env event after plugins load
  window.addEventListener('aegis:boot-complete', () => {
    window.dispatchEvent(new CustomEvent('aegis:env-change', {
      detail: { env: currentEnv, previousEnv: null }
    }));
  });

  console.log('[AEGIS] Env Selector loaded. Current:', currentEnv);
})();
