/**
 * AEGIS CONTROL — Camera Presence Plugin
 * Displays camera feeds and presence detection status.
 */
(function() {
  'use strict';

  const container = document.getElementById('camera-presence-body');
  if (!container) return;

  let cameras = {};
  let currentEnv = 'ALL';

  // ── Inject CSS ──
  const style = document.createElement('style');
  style.textContent = `
    .camera-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 8px;
      padding: 4px 0;
    }
    .camera-card {
      background: var(--aegis-bg);
      border: 1px solid var(--aegis-border);
      overflow: hidden;
      transition: border-color 0.3s;
    }
    .camera-card:hover {
      border-color: var(--aegis-dim);
    }
    .camera-card.env-filtered {
      display: none;
    }
    .camera-feed {
      height: 90px;
      background: #010608;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
    }
    .camera-feed-placeholder {
      color: var(--aegis-border);
      font-size: 10px;
      letter-spacing: 2px;
      text-transform: uppercase;
    }
    .camera-feed-noise {
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 100%;
      opacity: 0.03;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");
    }
    .camera-feed-scanline {
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 2px;
      background: rgba(0, 255, 136, 0.08);
      animation: cameraScanline 3s linear infinite;
    }
    @keyframes cameraScanline {
      0% { top: 0; }
      100% { top: 100%; }
    }
    .camera-info {
      padding: 8px 10px;
    }
    .camera-name {
      font-size: 11px;
      font-weight: 700;
      color: var(--aegis-text);
      letter-spacing: 1px;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .camera-status-dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .camera-status-dot.active {
      background: var(--aegis-primary);
      box-shadow: 0 0 4px rgba(0, 255, 136, 0.5);
    }
    .camera-status-dot.inactive {
      background: var(--aegis-muted);
    }
    .camera-status-dot.alert {
      background: var(--aegis-critical);
      box-shadow: 0 0 4px rgba(255, 51, 51, 0.5);
      animation: cameraDotPulse 1s infinite;
    }
    @keyframes cameraDotPulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    .camera-meta {
      display: flex;
      justify-content: space-between;
      font-size: 9px;
      color: var(--aegis-muted);
      letter-spacing: 1px;
    }
    .camera-presence-label {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .camera-presence-active {
      color: var(--aegis-warning);
      font-weight: 700;
    }
    .camera-motion-bar {
      height: 2px;
      background: var(--aegis-border);
      margin-top: 6px;
    }
    .camera-motion-fill {
      height: 100%;
      background: var(--aegis-primary);
      transition: width 0.5s ease;
    }
    .camera-motion-fill.motion-high {
      background: var(--aegis-warning);
    }
    .camera-motion-fill.motion-alert {
      background: var(--aegis-critical);
    }
    .camera-summary {
      display: flex;
      gap: 16px;
      padding: 8px 0;
      margin-bottom: 8px;
      border-bottom: 1px solid var(--aegis-border);
      font-size: 11px;
    }
    .camera-summary-item {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--aegis-muted);
    }
    .camera-summary-value {
      font-weight: 700;
      color: var(--aegis-text);
    }
  `;
  document.head.appendChild(style);

  // ── Render ──
  function render() {
    const cameraList = Object.values(cameras);

    if (cameraList.length === 0) {
      container.innerHTML = '<div style="color: var(--aegis-muted); text-align: center; padding: 20px; letter-spacing: 2px;">NO FEEDS ACTIVE</div>';
      return;
    }

    const active = cameraList.filter(c => c.status === 'active' || c.status === 'online').length;
    const motionCount = cameraList.filter(c => c.motion || c.presence).length;

    let html = `
      <div class="camera-summary">
        <div class="camera-summary-item">
          <span class="camera-summary-value">${cameraList.length}</span> CAMERAS
        </div>
        <div class="camera-summary-item">
          <span class="camera-summary-value text-primary">${active}</span> ACTIVE
        </div>
        <div class="camera-summary-item">
          <span class="camera-summary-value ${motionCount > 0 ? 'text-warning' : ''}">${motionCount}</span> MOTION
        </div>
      </div>
      <div class="camera-grid">
    `;

    cameraList.forEach(camera => {
      const env = (camera.environment || camera.env || 'UNKNOWN').toUpperCase();
      const envFiltered = (currentEnv !== 'ALL' && env !== currentEnv) ? 'env-filtered' : '';
      const status = camera.status || 'inactive';
      const dotClass = camera.alert ? 'alert' : (status === 'active' || status === 'online') ? 'active' : 'inactive';
      const motionLevel = camera.motion_level || camera.motionLevel || 0;
      const motionClass = motionLevel > 80 ? 'motion-alert' : motionLevel > 40 ? 'motion-high' : '';
      const presence = camera.presence || camera.persons_detected || 0;
      const lastEvent = camera.last_event || '';

      html += `
        <div class="camera-card ${envFiltered}" data-env="${env}">
          <div class="camera-feed">
            <div class="camera-feed-noise"></div>
            <div class="camera-feed-scanline"></div>
            <span class="camera-feed-placeholder">${camera.thumbnail ? '' : 'NO SIGNAL'}</span>
          </div>
          <div class="camera-info">
            <div class="camera-name">
              <span class="camera-status-dot ${dotClass}"></span>
              ${escapeHtml(camera.name || camera.id || 'CAM')}
            </div>
            <div class="camera-meta">
              <span>${env}</span>
              <span class="camera-presence-label">
                ${presence > 0 ? `<span class="camera-presence-active">PRESENCE: ${presence}</span>` : 'NO PRESENCE'}
              </span>
            </div>
            <div class="camera-motion-bar">
              <div class="camera-motion-fill ${motionClass}" style="width: ${motionLevel}%"></div>
            </div>
          </div>
        </div>
      `;
    });

    html += '</div>';
    container.innerHTML = html;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Event listeners ──
  window.addEventListener('aegis:camera', function(e) {
    const data = e.detail;
    if (data.cameras && Array.isArray(data.cameras)) {
      data.cameras.forEach(c => {
        cameras[c.id || c.name] = c;
      });
    } else if (data.id || data.name) {
      cameras[data.id || data.name] = data;
    }
    render();
  });

  window.addEventListener('aegis:env-change', function(e) {
    currentEnv = e.detail.env;
    const cards = container.querySelectorAll('.camera-card');
    cards.forEach(card => {
      if (currentEnv === 'ALL' || card.dataset.env === currentEnv) {
        card.classList.remove('env-filtered');
      } else {
        card.classList.add('env-filtered');
      }
    });
  });

  // ── Demo data after 10s if no real data ──
  setTimeout(() => {
    if (Object.keys(cameras).length === 0) {
      const demoCameras = [
        { id: 'cam-front', name: 'FRONT ENTRANCE', status: 'active', environment: 'CEDERVALL', motion_level: 12, presence: 0 },
        { id: 'cam-rear', name: 'REAR YARD', status: 'active', environment: 'CEDERVALL', motion_level: 0, presence: 0 },
        { id: 'cam-garage', name: 'GARAGE BAY', status: 'active', environment: 'CEDERVALL', motion_level: 5, presence: 0 },
        { id: 'cam-drive', name: 'DRIVEWAY', status: 'active', environment: 'CEDERVALL', motion_level: 22, presence: 1 },
        { id: 'cam-vlx-01', name: 'VLX MAIN', status: 'active', environment: 'VALVX', motion_level: 45, presence: 2 },
        { id: 'cam-vlx-02', name: 'VLX PERIMETER', status: 'active', environment: 'VALVX', motion_level: 8, presence: 0 },
        { id: 'cam-gwsk', name: 'GWSK LOBBY', status: 'inactive', environment: 'GWSK', motion_level: 0, presence: 0 },
        { id: 'cam-pers', name: 'HOME OFFICE', status: 'active', environment: 'PERSONAL', motion_level: 3, presence: 1 },
      ];

      demoCameras.forEach(c => { cameras[c.id] = c; });
      render();
    }
  }, 10000);

  console.log('[AEGIS] Camera Presence plugin loaded');
})();
