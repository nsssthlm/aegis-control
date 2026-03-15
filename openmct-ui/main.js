/**
 * AEGIS CONTROL — WebSocket Client & Event Bus
 * Manages connection to the gateway WebSocket and routes events to panels.
 */
(function() {
  'use strict';

  const WS_URL = (() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = location.hostname || 'localhost';
    return `${proto}//${host}:8001/ws`;
  })();

  const MAX_BACKOFF = 30000;
  const THREAT_WINDOW_MS = 30 * 60 * 1000; // 30 minutes

  let ws = null;
  let reconnectAttempts = 0;
  let reconnectTimer = null;
  let recentEvents = []; // events from last 30 min for threat calc
  let connected = false;

  // ── Connection status UI ──
  const connectionDot = document.getElementById('connection-dot');
  const connectionText = document.getElementById('connection-text');
  const threatValue = document.getElementById('threat-value');

  function setConnectionStatus(isConnected) {
    connected = isConnected;
    if (connectionDot) {
      connectionDot.classList.toggle('connected', isConnected);
    }
    if (connectionText) {
      connectionText.textContent = isConnected ? 'CONNECTED' : 'DISCONNECTED';
      connectionText.style.color = isConnected ? 'var(--aegis-primary)' : 'var(--aegis-critical)';
    }
  }

  // ── UTC Clock ──
  function updateClock() {
    const el = document.getElementById('header-time');
    if (!el) return;
    const now = new Date();
    const h = String(now.getUTCHours()).padStart(2, '0');
    const m = String(now.getUTCMinutes()).padStart(2, '0');
    const s = String(now.getUTCSeconds()).padStart(2, '0');
    const day = String(now.getUTCDate()).padStart(2, '0');
    const mon = String(now.getUTCMonth() + 1).padStart(2, '0');
    const yr = now.getUTCFullYear();
    el.textContent = `${yr}-${mon}-${day} ${h}:${m}:${s} UTC`;
  }
  setInterval(updateClock, 1000);
  updateClock();

  // ── Threat Level Calculation ──
  function calculateThreatLevel() {
    const now = Date.now();
    // Prune old events
    recentEvents = recentEvents.filter(e => (now - e.time) < THREAT_WINDOW_MS);

    let score = 0;
    recentEvents.forEach(e => {
      const severity = (e.severity || '').toUpperCase();
      switch (severity) {
        case 'CRITICAL': score += 10; break;
        case 'INTRUSION': score += 15; break;
        case 'SENSITIVE': score += 8; break;
        case 'WARNING': score += 3; break;
        case 'INFO': score += 0.5; break;
      }

      const type = (e.type || '').toUpperCase();
      if (type.includes('INTRUSION') || type.includes('BREACH')) score += 10;
      if (type.includes('MOTION') && severity !== 'INFO') score += 2;
    });

    let level, className;
    if (score >= 80) { level = 'SEVERE'; className = 'threat-severe'; }
    else if (score >= 40) { level = 'HIGH'; className = 'threat-high'; }
    else if (score >= 20) { level = 'ELEVATED'; className = 'threat-elevated'; }
    else if (score >= 5) { level = 'GUARDED'; className = 'threat-guarded'; }
    else { level = 'LOW'; className = 'threat-low'; }

    if (threatValue) {
      threatValue.textContent = level;
      threatValue.className = className;
    }

    return { level, score };
  }

  // Recalculate every 15 seconds
  setInterval(calculateThreatLevel, 15000);

  // ── WebSocket Connection ──
  function connect() {
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
      return;
    }

    try {
      ws = new WebSocket(WS_URL);
    } catch (err) {
      console.error('[AEGIS] WebSocket creation failed:', err);
      scheduleReconnect();
      return;
    }

    ws.onopen = function() {
      console.log('[AEGIS] WebSocket connected to', WS_URL);
      reconnectAttempts = 0;
      setConnectionStatus(true);

      // Send initial handshake
      ws.send(JSON.stringify({
        type: 'CLIENT_HELLO',
        client: 'aegis-control-ui',
        version: '4.0.0',
        timestamp: new Date().toISOString()
      }));

      window.dispatchEvent(new CustomEvent('aegis:connected'));
    };

    ws.onmessage = function(event) {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        console.warn('[AEGIS] Non-JSON message:', event.data);
        return;
      }

      // Respond to PING
      if (data.type === 'PING') {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'PONG', timestamp: new Date().toISOString() }));
        }
        return;
      }

      // Track for threat calculation
      if (data.severity || data.event_type) {
        recentEvents.push({
          time: Date.now(),
          severity: data.severity || data.level || 'INFO',
          type: data.event_type || data.type || ''
        });
        calculateThreatLevel();
      }

      // Route events via CustomEvent
      routeEvent(data);
    };

    ws.onclose = function(event) {
      console.log('[AEGIS] WebSocket closed:', event.code, event.reason);
      setConnectionStatus(false);
      window.dispatchEvent(new CustomEvent('aegis:disconnected'));
      scheduleReconnect();
    };

    ws.onerror = function(err) {
      console.error('[AEGIS] WebSocket error:', err);
      setConnectionStatus(false);
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    const delay = Math.min(Math.pow(2, reconnectAttempts) * 1000, MAX_BACKOFF);
    reconnectAttempts++;
    console.log(`[AEGIS] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);

    const footerMsg = document.getElementById('footer-msg');
    if (footerMsg) {
      footerMsg.textContent = `RECONNECTING IN ${Math.round(delay / 1000)}s...`;
      footerMsg.style.color = 'var(--aegis-warning)';
    }

    reconnectTimer = setTimeout(() => {
      connect();
    }, delay);
  }

  function routeEvent(data) {
    const eventType = data.type || data.event_type || 'UNKNOWN';

    // General event for all listeners
    window.dispatchEvent(new CustomEvent('aegis:event', { detail: data }));

    // Route by type
    switch (eventType) {
      case 'ALERT':
      case 'MOTION':
      case 'INTRUSION':
      case 'CAMERA_EVENT':
      case 'SYSTEM_EVENT':
      case 'ACCESS_EVENT':
        window.dispatchEvent(new CustomEvent('aegis:alert', { detail: data }));
        break;

      case 'SERVER_STATUS':
      case 'SYSTEM_STATUS':
      case 'NODE_STATUS':
        window.dispatchEvent(new CustomEvent('aegis:server-status', { detail: data }));
        break;

      case 'CAMERA_FEED':
      case 'PRESENCE':
      case 'CAMERA_PRESENCE':
        window.dispatchEvent(new CustomEvent('aegis:camera', { detail: data }));
        break;

      case 'STATUS_SUMMARY':
      case 'MISSION_UPDATE':
        window.dispatchEvent(new CustomEvent('aegis:mission', { detail: data }));
        break;

      default:
        // Forward as generic alert for the feed
        window.dispatchEvent(new CustomEvent('aegis:alert', { detail: data }));
        break;
    }
  }

  // ── Expose send function globally ──
  window.aegisSend = function(message) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof message === 'string' ? message : JSON.stringify(message));
      return true;
    }
    return false;
  };

  // ── Expose connection state ──
  window.aegisConnected = function() {
    return connected;
  };

  // ── FPS Counter ──
  let frameCount = 0;
  let lastFpsTime = performance.now();
  const fpsEl = document.getElementById('footer-fps');

  function countFrame() {
    frameCount++;
    const now = performance.now();
    if (now - lastFpsTime >= 1000) {
      if (fpsEl) fpsEl.textContent = frameCount + ' FPS';
      frameCount = 0;
      lastFpsTime = now;
    }
    requestAnimationFrame(countFrame);
  }
  requestAnimationFrame(countFrame);

  // ── Start connection after boot ──
  window.addEventListener('aegis:boot-complete', () => {
    connect();
    const footerMsg = document.getElementById('footer-msg');
    if (footerMsg) {
      footerMsg.textContent = 'AEGIS CONTROL OPERATIONAL';
      footerMsg.style.color = '';
    }
  });

  // Also try connecting immediately if boot already happened
  if (!document.getElementById('boot-screen')) {
    connect();
  }

})();
