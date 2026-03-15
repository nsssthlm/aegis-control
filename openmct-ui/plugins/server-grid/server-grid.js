/**
 * AEGIS CONTROL — Server Grid Plugin
 * Displays server/node status in a grid layout.
 */
(function() {
  'use strict';

  const container = document.getElementById('server-grid-body');
  if (!container) return;

  let servers = {};
  let currentEnv = 'ALL';

  // ── Inject CSS ──
  const style = document.createElement('style');
  style.textContent = `
    .server-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 8px;
      padding: 4px 0;
    }
    .server-node {
      background: var(--aegis-bg);
      border: 1px solid var(--aegis-border);
      padding: 10px;
      position: relative;
      transition: border-color 0.3s, box-shadow 0.3s;
      cursor: default;
    }
    .server-node:hover {
      border-color: var(--aegis-dim);
      box-shadow: 0 0 12px rgba(0, 255, 136, 0.08);
    }
    .server-node.status-online {
      border-left: 3px solid var(--aegis-primary);
    }
    .server-node.status-warning {
      border-left: 3px solid var(--aegis-warning);
    }
    .server-node.status-offline {
      border-left: 3px solid var(--aegis-critical);
      opacity: 0.7;
    }
    .server-node.status-unknown {
      border-left: 3px solid var(--aegis-muted);
      opacity: 0.5;
    }
    .server-node-name {
      font-size: 11px;
      font-weight: 700;
      color: var(--aegis-text);
      letter-spacing: 1px;
      margin-bottom: 6px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .server-node-env {
      font-size: 9px;
      color: var(--aegis-muted);
      letter-spacing: 1px;
      margin-bottom: 6px;
    }
    .server-node-metrics {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .server-metric {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
    }
    .server-metric-label {
      color: var(--aegis-muted);
    }
    .server-metric-value {
      color: var(--aegis-dim);
      font-variant-numeric: tabular-nums;
    }
    .server-metric-value.high {
      color: var(--aegis-warning);
    }
    .server-metric-value.critical {
      color: var(--aegis-critical);
    }
    .server-node-status {
      position: absolute;
      top: 8px;
      right: 8px;
      width: 6px;
      height: 6px;
      border-radius: 50%;
    }
    .server-node-status.online {
      background: var(--aegis-primary);
      box-shadow: 0 0 6px rgba(0, 255, 136, 0.5);
    }
    .server-node-status.warning {
      background: var(--aegis-warning);
      box-shadow: 0 0 6px rgba(255, 170, 0, 0.5);
    }
    .server-node-status.offline {
      background: var(--aegis-critical);
      box-shadow: 0 0 6px rgba(255, 51, 51, 0.5);
    }
    .server-node-status.unknown {
      background: var(--aegis-muted);
    }
    .server-bar {
      height: 3px;
      background: var(--aegis-border);
      margin-top: 2px;
      border-radius: 1px;
      overflow: hidden;
    }
    .server-bar-fill {
      height: 100%;
      transition: width 0.5s ease;
      border-radius: 1px;
    }
    .server-summary {
      display: flex;
      gap: 16px;
      padding: 8px 0;
      margin-bottom: 8px;
      border-bottom: 1px solid var(--aegis-border);
      font-size: 11px;
    }
    .server-summary-item {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .server-summary-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
    }
    .server-summary-count {
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .server-node.env-filtered {
      display: none;
    }
  `;
  document.head.appendChild(style);

  // ── Render grid ──
  function render() {
    const serverList = Object.values(servers);

    if (serverList.length === 0) {
      container.innerHTML = '<div style="color: var(--aegis-muted); text-align: center; padding: 20px; letter-spacing: 2px;">SCANNING NODES...</div>';
      return;
    }

    // Summary
    let online = 0, warning = 0, offline = 0;
    serverList.forEach(s => {
      const status = (s.status || 'unknown').toLowerCase();
      if (status === 'online' || status === 'nominal') online++;
      else if (status === 'warning' || status === 'degraded') warning++;
      else if (status === 'offline' || status === 'error') offline++;
    });

    let html = `
      <div class="server-summary">
        <div class="server-summary-item">
          <div class="server-summary-dot" style="background: var(--aegis-primary);"></div>
          <span class="server-summary-count text-primary">${online}</span>
          <span class="text-muted">ONLINE</span>
        </div>
        <div class="server-summary-item">
          <div class="server-summary-dot" style="background: var(--aegis-warning);"></div>
          <span class="server-summary-count text-warning">${warning}</span>
          <span class="text-muted">WARNING</span>
        </div>
        <div class="server-summary-item">
          <div class="server-summary-dot" style="background: var(--aegis-critical);"></div>
          <span class="server-summary-count text-critical">${offline}</span>
          <span class="text-muted">OFFLINE</span>
        </div>
      </div>
      <div class="server-grid">
    `;

    serverList.forEach(server => {
      const status = normalizeStatus(server.status);
      const env = (server.environment || server.env || 'UNKNOWN').toUpperCase();
      const envFiltered = (currentEnv !== 'ALL' && env !== currentEnv) ? 'env-filtered' : '';
      const cpu = server.cpu || 0;
      const mem = server.memory || server.mem || 0;
      const disk = server.disk || 0;

      html += `
        <div class="server-node status-${status} ${envFiltered}" data-env="${env}">
          <div class="server-node-status ${status}"></div>
          <div class="server-node-name">${escapeHtml(server.name || server.id || 'NODE')}</div>
          <div class="server-node-env">${env}</div>
          <div class="server-node-metrics">
            <div class="server-metric">
              <span class="server-metric-label">CPU</span>
              <span class="server-metric-value ${cpu > 90 ? 'critical' : cpu > 70 ? 'high' : ''}">${cpu}%</span>
            </div>
            <div class="server-bar"><div class="server-bar-fill" style="width: ${cpu}%; background: ${cpu > 90 ? 'var(--aegis-critical)' : cpu > 70 ? 'var(--aegis-warning)' : 'var(--aegis-primary)'}"></div></div>
            <div class="server-metric">
              <span class="server-metric-label">MEM</span>
              <span class="server-metric-value ${mem > 90 ? 'critical' : mem > 70 ? 'high' : ''}">${mem}%</span>
            </div>
            <div class="server-bar"><div class="server-bar-fill" style="width: ${mem}%; background: ${mem > 90 ? 'var(--aegis-critical)' : mem > 70 ? 'var(--aegis-warning)' : 'var(--aegis-dim)'}"></div></div>
            ${disk ? `
            <div class="server-metric">
              <span class="server-metric-label">DISK</span>
              <span class="server-metric-value ${disk > 90 ? 'critical' : disk > 80 ? 'high' : ''}">${disk}%</span>
            </div>
            ` : ''}
          </div>
        </div>
      `;
    });

    html += '</div>';
    container.innerHTML = html;
  }

  function normalizeStatus(status) {
    if (!status) return 'unknown';
    const s = status.toLowerCase();
    if (s === 'online' || s === 'nominal' || s === 'ok' || s === 'healthy') return 'online';
    if (s === 'warning' || s === 'degraded' || s === 'slow') return 'warning';
    if (s === 'offline' || s === 'error' || s === 'down' || s === 'critical') return 'offline';
    return 'unknown';
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Event listeners ──
  window.addEventListener('aegis:server-status', function(e) {
    const data = e.detail;
    if (data.servers && Array.isArray(data.servers)) {
      // Batch update
      data.servers.forEach(s => {
        servers[s.id || s.name] = s;
      });
    } else if (data.id || data.name) {
      servers[data.id || data.name] = data;
    }
    render();
  });

  window.addEventListener('aegis:env-change', function(e) {
    currentEnv = e.detail.env;
    // Re-filter existing nodes
    const nodes = container.querySelectorAll('.server-node');
    nodes.forEach(node => {
      if (currentEnv === 'ALL' || node.dataset.env === currentEnv) {
        node.classList.remove('env-filtered');
      } else {
        node.classList.add('env-filtered');
      }
    });
  });

  // ── Generate demo data if no real data after 10s ──
  setTimeout(() => {
    if (Object.keys(servers).length === 0) {
      const demoServers = [
        { id: 'gw-01', name: 'GW-PRIMARY', status: 'online', environment: 'CEDERVALL', cpu: 23, memory: 45, disk: 32 },
        { id: 'gw-02', name: 'GW-BACKUP', status: 'online', environment: 'CEDERVALL', cpu: 12, memory: 38, disk: 28 },
        { id: 'cam-01', name: 'CAM-PROCESSOR', status: 'online', environment: 'CEDERVALL', cpu: 67, memory: 72, disk: 55 },
        { id: 'db-01', name: 'DB-PRIMARY', status: 'online', environment: 'CEDERVALL', cpu: 34, memory: 61, disk: 44 },
        { id: 'ai-01', name: 'AI-CORTEX', status: 'online', environment: 'CEDERVALL', cpu: 45, memory: 58, disk: 30 },
        { id: 'vlx-01', name: 'VLX-NODE-1', status: 'online', environment: 'VALVX', cpu: 19, memory: 33, disk: 22 },
        { id: 'vlx-02', name: 'VLX-NODE-2', status: 'warning', environment: 'VALVX', cpu: 78, memory: 82, disk: 67 },
        { id: 'gwsk-01', name: 'GWSK-EDGE', status: 'online', environment: 'GWSK', cpu: 15, memory: 29, disk: 18 },
        { id: 'pers-01', name: 'PERS-HOME', status: 'online', environment: 'PERSONAL', cpu: 8, memory: 22, disk: 41 },
      ];

      demoServers.forEach(s => { servers[s.id] = s; });
      render();
    }
  }, 10000);

  console.log('[AEGIS] Server Grid plugin loaded');
})();
