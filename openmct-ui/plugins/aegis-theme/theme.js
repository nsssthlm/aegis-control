/**
 * AEGIS CONTROL — Theme Plugin
 * CRT scanlines, phosphor glow, and NASA ISS aesthetic
 */
(function() {
  'use strict';

  // Inject additional theme CSS
  const style = document.createElement('style');
  style.textContent = `
    /* ═══════════════════════════════════════════════════════════════
       AEGIS THEME — CRT PHOSPHOR / NASA ISS AESTHETIC
       ═══════════════════════════════════════════════════════════════ */

    /* ─── ENHANCED CRT EFFECT ─── */
    #crt-overlay {
      mix-blend-mode: multiply;
    }

    /* Subtle screen flicker */
    @keyframes crt-flicker {
      0% { opacity: 0.98; }
      5% { opacity: 0.99; }
      10% { opacity: 0.97; }
      15% { opacity: 1; }
      20% { opacity: 0.98; }
      50% { opacity: 1; }
      80% { opacity: 0.99; }
      85% { opacity: 0.97; }
      90% { opacity: 1; }
      95% { opacity: 0.98; }
      100% { opacity: 1; }
    }

    /* Phosphor glow on text */
    .panel-header {
      text-shadow: 0 0 4px rgba(0, 119, 68, 0.4);
    }

    #header-logo {
      text-shadow:
        0 0 7px rgba(0, 255, 136, 0.4),
        0 0 20px rgba(0, 255, 136, 0.15);
    }

    /* ─── PANEL DEPTH & BEVELS ─── */
    .panel {
      box-shadow:
        inset 0 1px 0 rgba(0, 255, 136, 0.03),
        inset 0 -1px 0 rgba(0, 0, 0, 0.3);
    }

    .panel-header {
      position: relative;
    }
    .panel-header::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(
        90deg,
        transparent 0%,
        var(--aegis-border) 20%,
        var(--aegis-dim) 50%,
        var(--aegis-border) 80%,
        transparent 100%
      );
      opacity: 0.5;
    }

    /* ─── CORNER ACCENTS (NASA-style) ─── */
    .panel::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 12px;
      height: 12px;
      border-top: 1px solid var(--aegis-dim);
      border-left: 1px solid var(--aegis-dim);
      opacity: 0.4;
      pointer-events: none;
    }
    .panel::after {
      content: '';
      position: absolute;
      bottom: 0;
      right: 0;
      width: 12px;
      height: 12px;
      border-bottom: 1px solid var(--aegis-dim);
      border-right: 1px solid var(--aegis-dim);
      opacity: 0.4;
      pointer-events: none;
    }
    .panel {
      position: relative;
    }

    /* ─── INPUT STYLING ─── */
    input, textarea, select {
      background: var(--aegis-bg);
      border: 1px solid var(--aegis-border);
      color: var(--aegis-text);
      font-family: var(--aegis-font);
      font-size: 12px;
      padding: 6px 10px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    input:focus, textarea:focus, select:focus {
      border-color: var(--aegis-dim);
      box-shadow: 0 0 8px rgba(0, 255, 136, 0.15), inset 0 0 4px rgba(0, 255, 136, 0.05);
    }

    /* ─── BUTTON STYLING ─── */
    button, .btn {
      background: linear-gradient(180deg, var(--aegis-surface) 0%, var(--aegis-bg) 100%);
      border: 1px solid var(--aegis-border);
      color: var(--aegis-primary);
      font-family: var(--aegis-font);
      font-size: 11px;
      padding: 6px 16px;
      cursor: pointer;
      text-transform: uppercase;
      letter-spacing: 2px;
      transition: all 0.15s;
      font-weight: 700;
    }
    button:hover, .btn:hover {
      border-color: var(--aegis-dim);
      background: linear-gradient(180deg, rgba(0,255,136,0.08) 0%, var(--aegis-surface) 100%);
      box-shadow: 0 0 12px rgba(0, 255, 136, 0.15);
      text-shadow: 0 0 6px rgba(0, 255, 136, 0.4);
    }
    button:active, .btn:active {
      transform: translateY(1px);
      background: var(--aegis-bg);
    }
    button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    /* ─── TABLE STYLING ─── */
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }
    th {
      text-align: left;
      padding: 6px 8px;
      color: var(--aegis-muted);
      font-weight: 700;
      letter-spacing: 2px;
      text-transform: uppercase;
      font-size: 10px;
      border-bottom: 1px solid var(--aegis-border);
      background: rgba(0, 255, 136, 0.02);
    }
    td {
      padding: 5px 8px;
      border-bottom: 1px solid rgba(10, 48, 64, 0.4);
      color: var(--aegis-text);
    }
    tr:hover td {
      background: rgba(0, 255, 136, 0.03);
    }
    tr {
      cursor: default;
    }

    /* ─── SELECTION ─── */
    ::selection {
      background: rgba(0, 255, 136, 0.2);
      color: var(--aegis-primary);
    }

    /* ─── RESPONSIVE GRID ─── */
    @media (max-width: 1200px) {
      #main-grid {
        grid-template-columns: 280px 1fr;
      }
    }
    @media (max-width: 900px) {
      #main-grid {
        grid-template-columns: 1fr;
        grid-template-rows: auto auto auto auto auto;
      }
      #panel-mission { grid-column: 1; grid-row: 1; min-height: 200px; }
      #panel-alerts { grid-column: 1; grid-row: 2; min-height: 250px; }
      #panel-system { grid-column: 1; grid-row: 3; min-height: 200px; }
      #panel-camera { grid-column: 1; grid-row: 4; min-height: 200px; }
      #panel-ai { grid-column: 1; grid-row: 5; }
    }

    /* ─── NASA HAZARD STRIPE (top accent) ─── */
    #header::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: linear-gradient(
        90deg,
        var(--aegis-primary) 0%,
        var(--aegis-dim) 30%,
        transparent 50%,
        var(--aegis-dim) 70%,
        var(--aegis-primary) 100%
      );
      opacity: 0.6;
    }
    #header {
      position: relative;
    }

    /* ─── LOADING SPINNER ─── */
    @keyframes aegis-spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    .aegis-spinner {
      width: 20px;
      height: 20px;
      border: 2px solid var(--aegis-border);
      border-top-color: var(--aegis-primary);
      border-radius: 50%;
      animation: aegis-spin 1s linear infinite;
      display: inline-block;
    }

    /* ─── HORIZONTAL RULE ─── */
    .aegis-hr {
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--aegis-border), transparent);
      margin: 8px 0;
      border: none;
    }

    /* ─── BADGE / TAG ─── */
    .aegis-badge {
      display: inline-block;
      padding: 1px 6px;
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      border: 1px solid;
      border-radius: 2px;
    }
    .aegis-badge-info { color: var(--aegis-primary); border-color: var(--aegis-dim); }
    .aegis-badge-warning { color: var(--aegis-warning); border-color: #886600; }
    .aegis-badge-critical { color: var(--aegis-critical); border-color: #880000; }
    .aegis-badge-intrusion { color: var(--aegis-intrusion); border-color: #880033; }
    .aegis-badge-sensitive { color: var(--aegis-sensitive); border-color: #884400; }
  `;

  document.head.appendChild(style);

  console.log('[AEGIS] Theme loaded: NASA ISS CRT Phosphor');
})();
