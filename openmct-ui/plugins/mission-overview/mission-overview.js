/**
 * AEGIS CONTROL — Mission Overview Plugin
 * Polls GET /api/status/summary every 30s.
 * Table: ENV | STATUS | ALERTS 24H | THREAT LEVEL | LAST EVENT
 * Click row to change environment.
 */
(function() {
  'use strict';

  const container = document.getElementById('mission-overview-body');
  if (!container) return;

  const STATUS_URL = '/api/status/summary';
  const POLL_INTERVAL = 30000; // 30 seconds

  let envData = {};
  let pollTimer = null;
  let currentEnv = 'ALL';

  // ── Inject CSS ──
  const style = document.createElement('style');
  style.textContent = `
    .mission-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 10px;
    }
    .mission-table th {
      text-align: left;
      padding: 6px 6px;
      color: var(--aegis-muted);
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      font-size: 9px;
      border-bottom: 1px solid var(--aegis-border);
      background: rgba(0, 255, 136, 0.02);
      white-space: nowrap;
    }
    .mission-table td {
      padding: 6px 6px;
      border-bottom: 1px solid rgba(10, 48, 64, 0.3);
      color: var(--aegis-text);
      font-size: 11px;
      white-space: nowrap;
    }
    .mission-table tr.clickable {
      cursor: pointer;
      transition: background 0.15s;
    }
    .mission-table tr.clickable:hover td {
      background: rgba(0, 255, 136, 0.05);
    }
    .mission-table tr.active td {
      background: rgba(0, 255, 136, 0.08);
      border-left: 2px solid var(--aegis-primary);
    }
    .mission-status {
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .mission-status-dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
    }
    .mission-status-dot.nominal {
      background: var(--aegis-primary);
      box-shadow: 0 0 4px rgba(0, 255, 136, 0.5);
    }
    .mission-status-dot.degraded {
      background: var(--aegis-warning);
      box-shadow: 0 0 4px rgba(255, 170, 0, 0.5);
    }
    .mission-status-dot.critical {
      background: var(--aegis-critical);
      box-shadow: 0 0 4px rgba(255, 51, 51, 0.5);
      animation: missionDotPulse 1s infinite;
    }
    .mission-status-dot.offline {
      background: var(--aegis-muted);
    }
    @keyframes missionDotPulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    .mission-threat {
      padding: 1px 6px;
      border: 1px solid;
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
    }
    .mission-threat-low { color: var(--aegis-primary); border-color: var(--aegis-dim); }
    .mission-threat-guarded { color: #00ccff; border-color: #006688; }
    .mission-threat-elevated { color: var(--aegis-warning); border-color: #886600; }
    .mission-threat-high { color: var(--aegis-sensitive); border-color: #884400; }
    .mission-threat-severe { color: var(--aegis-critical); border-color: #880000; }
    .mission-alerts-count {
      font-variant-numeric: tabular-nums;
    }
    .mission-alerts-count.high {
      color: var(--aegis-warning);
      font-weight: 700;
    }
    .mission-alerts-count.critical {
      color: var(--aegis-critical);
      font-weight: 700;
    }
    .mission-last-event {
      color: var(--aegis-muted);
      font-size: 10px;
      max-width: 100px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .mission-uptime {
      margin-top: 12px;
      padding-top: 8px;
      border-top: 1px solid var(--aegis-border);
      font-size: 10px;
      color: var(--aegis-muted);
      display: flex;
      justify-content: space-between;
    }
    .mission-uptime-value {
      color: var(--aegis-dim);
      font-weight: 700;
    }
  `;
  document.head.appendChild(style);

  // ── Render ──
  function render() {
    const envList = Object.values(envData);

    if (envList.length === 0) {
      container.innerHTML = '<div style="color: var(--aegis-muted); text-align: center; padding: 20px; letter-spacing: 2px;">AWAITING TELEMETRY...</div>';
      return;
    }

    let html = `
      <table class="mission-table">
        <thead>
          <tr>
            <th>ENV</th>
            <th>STATUS</th>
            <th>24H</th>
            <th>THREAT</th>
            <th>LAST EVENT</th>
          </tr>
        </thead>
        <tbody>
    `;

    envList.forEach(env => {
      const statusClass = normalizeStatusClass(env.status);
      const threatClass = (env.threat_level || 'low').toLowerCase();
      const alertCount = env.alerts_24h || env.alerts || 0;
      const alertClass = alertCount > 50 ? 'critical' : alertCount > 20 ? 'high' : '';
      const isActive = currentEnv === env.name;
      const lastEvent = env.last_event || env.lastEvent || '--';
      const lastEventTime = formatRelativeTime(env.last_event_time || env.lastEventTime);

      html += `
        <tr class="clickable ${isActive ? 'active' : ''}" data-env="${escapeHtml(env.name)}">
          <td style="font-weight: 700; letter-spacing: 2px;">${escapeHtml(env.name)}</td>
          <td>
            <span class="mission-status">
              <span class="mission-status-dot ${statusClass}"></span>
              ${statusLabel(statusClass)}
            </span>
          </td>
          <td><span class="mission-alerts-count ${alertClass}">${alertCount}</span></td>
          <td><span class="mission-threat mission-threat-${threatClass}">${(env.threat_level || 'LOW').toUpperCase()}</span></td>
          <td class="mission-last-event" title="${escapeHtml(lastEvent)}">${lastEventTime}</td>
        </tr>
      `;
    });

    html += `
        </tbody>
      </table>
      <div class="mission-uptime">
        <span>SYSTEM UPTIME</span>
        <span class="mission-uptime-value">${formatUptime()}</span>
      </div>
    `;

    container.innerHTML = html;

    // Add click handlers
    container.querySelectorAll('tr.clickable').forEach(row => {
      row.addEventListener('click', () => {
        const env = row.dataset.env;
        if (typeof window.aegisSetEnv === 'function') {
          window.aegisSetEnv(env);
        }
      });
    });
  }

  function normalizeStatusClass(status) {
    if (!status) return 'offline';
    const s = status.toLowerCase();
    if (s === 'nominal' || s === 'online' || s === 'ok' || s === 'healthy') return 'nominal';
    if (s === 'degraded' || s === 'warning' || s === 'slow') return 'degraded';
    if (s === 'critical' || s === 'error' || s === 'down') return 'critical';
    return 'offline';
  }

  function statusLabel(cls) {
    switch (cls) {
      case 'nominal': return '<span style="color: var(--aegis-primary);">NOMINAL</span>';
      case 'degraded': return '<span style="color: var(--aegis-warning);">DEGRADED</span>';
      case 'critical': return '<span style="color: var(--aegis-critical);">CRITICAL</span>';
      default: return '<span style="color: var(--aegis-muted);">OFFLINE</span>';
    }
  }

  function formatRelativeTime(timestamp) {
    if (!timestamp) return '--';
    try {
      const diff = Date.now() - new Date(timestamp).getTime();
      if (diff < 60000) return Math.round(diff / 1000) + 's ago';
      if (diff < 3600000) return Math.round(diff / 60000) + 'm ago';
      if (diff < 86400000) return Math.round(diff / 3600000) + 'h ago';
      return Math.round(diff / 86400000) + 'd ago';
    } catch {
      return '--';
    }
  }

  function formatUptime() {
    const seconds = Math.floor(performance.now() / 1000);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Poll API ──
  async function fetchSummary() {
    try {
      const response = await fetch(STATUS_URL);
      if (response.ok) {
        const data = await response.json();
        if (data.environments && Array.isArray(data.environments)) {
          data.environments.forEach(env => {
            envData[env.name] = env;
          });
        } else if (data.summary && Array.isArray(data.summary)) {
          data.summary.forEach(env => {
            envData[env.name] = env;
          });
        }
        render();
      }
    } catch (err) {
      // API may not be available yet — use demo data
      if (Object.keys(envData).length === 0) {
        loadDemoData();
      }
    }
  }

  function loadDemoData() {
    const demo = [
      { name: 'CEDERVALL', status: 'nominal', alerts_24h: 12, threat_level: 'LOW', last_event: 'Motion detected front yard', last_event_time: new Date(Date.now() - 300000).toISOString() },
      { name: 'VALVX', status: 'nominal', alerts_24h: 34, threat_level: 'GUARDED', last_event: 'Door sensor triggered', last_event_time: new Date(Date.now() - 600000).toISOString() },
      { name: 'GWSK', status: 'degraded', alerts_24h: 8, threat_level: 'LOW', last_event: 'Camera offline', last_event_time: new Date(Date.now() - 7200000).toISOString() },
      { name: 'PERSONAL', status: 'nominal', alerts_24h: 3, threat_level: 'LOW', last_event: 'System check OK', last_event_time: new Date(Date.now() - 1800000).toISOString() },
    ];
    demo.forEach(e => { envData[e.name] = e; });
    render();
  }

  // ── Event listeners ──
  window.addEventListener('aegis:mission', function(e) {
    const data = e.detail;
    if (data.environments) {
      data.environments.forEach(env => {
        envData[env.name] = env;
      });
      render();
    }
  });

  window.addEventListener('aegis:env-change', function(e) {
    currentEnv = e.detail.env;
    // Highlight active row
    const rows = container.querySelectorAll('tr.clickable');
    rows.forEach(row => {
      row.classList.toggle('active', row.dataset.env === currentEnv);
    });
  });

  // ── Start polling after boot ──
  window.addEventListener('aegis:boot-complete', () => {
    fetchSummary();
    pollTimer = setInterval(fetchSummary, POLL_INTERVAL);

    // Update uptime display
    setInterval(() => {
      const uptimeEl = container.querySelector('.mission-uptime-value');
      if (uptimeEl) uptimeEl.textContent = formatUptime();
    }, 1000);
  });

  console.log('[AEGIS] Mission Overview plugin loaded');
})();
