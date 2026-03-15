/**
 * AEGIS CONTROL — Alert Feed Plugin
 * Live event feed with color-coded severity, animations, and env filtering.
 */
(function() {
  'use strict';

  const MAX_EVENTS = 100;
  const container = document.getElementById('alert-feed-body');
  const countEl = document.getElementById('alert-count');
  const indicator = document.getElementById('alert-indicator');
  if (!container) return;

  let events = [];
  let currentEnv = 'ALL';
  let totalCount = 0;

  // ── Severity colors and behavior ──
  const SEVERITY_CONFIG = {
    INFO:      { color: '#00ff88', border: '#00ff88', anim: null },
    WARNING:   { color: '#ffaa00', border: '#ffaa00', anim: null },
    CRITICAL:  { color: '#ff3333', border: '#ff3333', anim: 'pulse' },
    INTRUSION: { color: '#ff0066', border: '#ff0066', anim: 'blink-3x' },
    SENSITIVE: { color: '#ff6600', border: '#ff6600', anim: null }
  };

  // ── Inject CSS ──
  const style = document.createElement('style');
  style.textContent = `
    .alert-item {
      display: flex;
      gap: 10px;
      padding: 6px 10px;
      border-left: 3px solid var(--aegis-border);
      margin-bottom: 4px;
      background: rgba(0, 0, 0, 0.2);
      animation: alertSlideIn 0.3s ease-out;
      transition: opacity 0.2s;
      font-size: 11px;
      align-items: flex-start;
    }
    .alert-item.filtered-out {
      display: none;
    }
    .alert-item:hover {
      background: rgba(0, 255, 136, 0.03);
    }

    @keyframes alertSlideIn {
      from { transform: translateX(-20px); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }

    @keyframes alertPulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }

    @keyframes alertBlink3x {
      0% { opacity: 1; }
      10% { opacity: 0; }
      20% { opacity: 1; }
      30% { opacity: 0; }
      40% { opacity: 1; }
      50% { opacity: 0; }
      60% { opacity: 1; }
      100% { opacity: 1; }
    }

    .alert-item.anim-pulse {
      animation: alertSlideIn 0.3s ease-out, alertPulse 1.5s ease-in-out 3;
    }
    .alert-item.anim-blink-3x {
      animation: alertSlideIn 0.3s ease-out, alertBlink3x 1.2s ease-in-out 1;
    }

    .alert-time {
      color: var(--aegis-muted);
      white-space: nowrap;
      font-size: 10px;
      min-width: 65px;
      padding-top: 1px;
      font-variant-numeric: tabular-nums;
    }
    .alert-severity {
      font-weight: 700;
      font-size: 9px;
      letter-spacing: 1px;
      min-width: 70px;
      padding: 1px 4px;
      text-align: center;
      border: 1px solid;
      border-radius: 2px;
      flex-shrink: 0;
    }
    .alert-env {
      color: var(--aegis-muted);
      font-size: 9px;
      letter-spacing: 1px;
      min-width: 55px;
      flex-shrink: 0;
    }
    .alert-message {
      flex: 1;
      color: var(--aegis-text);
      word-break: break-word;
      line-height: 1.4;
    }
    .alert-source {
      color: var(--aegis-muted);
      font-size: 10px;
      white-space: nowrap;
    }

    .alert-empty {
      color: var(--aegis-muted);
      text-align: center;
      padding: 40px 20px;
      font-size: 12px;
      letter-spacing: 2px;
    }
  `;
  document.head.appendChild(style);

  // ── Show empty state ──
  function showEmpty() {
    container.innerHTML = '<div class="alert-empty">AWAITING EVENTS...</div>';
  }
  showEmpty();

  // ── Format time ──
  function formatTime(timestamp) {
    try {
      const d = new Date(timestamp);
      const h = String(d.getUTCHours()).padStart(2, '0');
      const m = String(d.getUTCMinutes()).padStart(2, '0');
      const s = String(d.getUTCSeconds()).padStart(2, '0');
      return `${h}:${m}:${s}`;
    } catch {
      return '--:--:--';
    }
  }

  // ── Create alert element ──
  function createAlertElement(event) {
    const severity = (event.severity || event.level || 'INFO').toUpperCase();
    const config = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.INFO;
    const env = event.environment || event.env || 'UNKNOWN';
    const message = event.message || event.description || event.event_type || event.type || 'Unknown event';
    const source = event.source || event.camera || event.server || '';
    const time = formatTime(event.timestamp || new Date().toISOString());

    const el = document.createElement('div');
    el.className = 'alert-item';
    if (config.anim) el.classList.add('anim-' + config.anim);
    el.style.borderLeftColor = config.border;

    // Apply env filter
    if (currentEnv !== 'ALL' && env.toUpperCase() !== currentEnv) {
      el.classList.add('filtered-out');
    }

    el.dataset.env = env.toUpperCase();
    el.dataset.severity = severity;

    el.innerHTML = `
      <span class="alert-time">${time}</span>
      <span class="alert-severity" style="color: ${config.color}; border-color: ${config.color};">${severity}</span>
      <span class="alert-env">${env}</span>
      <span class="alert-message">${escapeHtml(message)}</span>
      ${source ? `<span class="alert-source">${escapeHtml(source)}</span>` : ''}
    `;

    return el;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Add event ──
  function addEvent(event) {
    // Remove empty state
    const emptyEl = container.querySelector('.alert-empty');
    if (emptyEl) emptyEl.remove();

    // Create element and prepend (newest on top)
    const el = createAlertElement(event);
    container.insertBefore(el, container.firstChild);
    events.unshift(event);
    totalCount++;

    // Trim to max
    while (events.length > MAX_EVENTS) {
      events.pop();
      const last = container.lastElementChild;
      if (last) last.remove();
    }

    // Update count
    updateCount();

    // Flash indicator
    flashIndicator(event);
  }

  function updateCount() {
    if (countEl) {
      const visible = container.querySelectorAll('.alert-item:not(.filtered-out)').length;
      countEl.textContent = `${visible} EVENTS`;
    }
  }

  function flashIndicator(event) {
    if (!indicator) return;
    const severity = (event.severity || 'INFO').toUpperCase();
    const config = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.INFO;
    indicator.style.background = config.color;
    indicator.style.boxShadow = `0 0 8px ${config.color}`;
    setTimeout(() => {
      indicator.style.background = '';
      indicator.style.boxShadow = '';
    }, 600);
  }

  // ── Filter by environment ──
  function filterByEnv(env) {
    currentEnv = env;
    const items = container.querySelectorAll('.alert-item');
    items.forEach(item => {
      if (env === 'ALL' || item.dataset.env === env) {
        item.classList.remove('filtered-out');
      } else {
        item.classList.add('filtered-out');
      }
    });
    updateCount();
  }

  // ── Event listeners ──
  window.addEventListener('aegis:alert', function(e) {
    addEvent(e.detail);
  });

  window.addEventListener('aegis:event', function(e) {
    // Also catch generic events that have alert-like data
    if (e.detail && e.detail.severity && !e.detail._routed) {
      // Already handled by aegis:alert
    }
  });

  window.addEventListener('aegis:env-change', function(e) {
    filterByEnv(e.detail.env);
  });

  console.log('[AEGIS] Alert Feed plugin loaded');
})();
