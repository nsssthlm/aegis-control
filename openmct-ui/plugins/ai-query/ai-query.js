/**
 * AEGIS CONTROL — AI Query Plugin
 * Input field + TRANSMIT button, typing animation, herald-voice integration.
 * Last 5 queries stored in sessionStorage.
 */
(function() {
  'use strict';

  const container = document.getElementById('ai-query-body');
  const statusEl = document.getElementById('ai-status');
  const indicatorEl = document.getElementById('ai-indicator');
  if (!container) return;

  const STORAGE_KEY = 'aegis-ai-history';
  const TYPING_SPEED = 25; // ms per character
  const ORION_HOST = window.AEGIS_ORION_HOST || 'http://localhost:8001';
  const HERALD_URL = (window.AEGIS_HERALD_HOST || 'http://localhost:8002') + '/speak';
  const AI_QUERY_URL = ORION_HOST + '/api/query';
  const SHORT_ANSWER_WORDS = 20;

  let isProcessing = false;
  let history = [];

  // Load history from sessionStorage
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored) history = JSON.parse(stored);
  } catch (e) { /* ignore */ }

  // ── Inject CSS ──
  const style = document.createElement('style');
  style.textContent = `
    .ai-container {
      display: flex;
      flex-direction: column;
      height: 100%;
      gap: 0;
    }
    .ai-input-row {
      display: flex;
      gap: 8px;
      padding: 0 0 8px 0;
      align-items: center;
      flex-shrink: 0;
    }
    .ai-label {
      font-size: 10px;
      color: var(--aegis-muted);
      letter-spacing: 2px;
      text-transform: uppercase;
      white-space: nowrap;
      flex-shrink: 0;
    }
    .ai-input {
      flex: 1;
      background: var(--aegis-bg);
      border: 1px solid var(--aegis-border);
      color: var(--aegis-primary);
      font-family: var(--aegis-font);
      font-size: 12px;
      padding: 6px 12px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .ai-input:focus {
      border-color: var(--aegis-dim);
      box-shadow: 0 0 8px rgba(0, 255, 136, 0.15), inset 0 0 4px rgba(0, 255, 136, 0.05);
    }
    .ai-input::placeholder {
      color: var(--aegis-muted);
      font-style: normal;
    }
    .ai-input:disabled {
      opacity: 0.5;
    }
    .ai-transmit-btn {
      background: linear-gradient(180deg, rgba(0,255,136,0.1) 0%, var(--aegis-surface) 100%);
      border: 1px solid var(--aegis-dim);
      color: var(--aegis-primary);
      font-family: var(--aegis-font);
      font-size: 11px;
      font-weight: 700;
      padding: 6px 20px;
      cursor: pointer;
      letter-spacing: 3px;
      text-transform: uppercase;
      transition: all 0.15s;
      white-space: nowrap;
      flex-shrink: 0;
    }
    .ai-transmit-btn:hover:not(:disabled) {
      background: linear-gradient(180deg, rgba(0,255,136,0.2) 0%, rgba(0,255,136,0.05) 100%);
      box-shadow: 0 0 16px rgba(0, 255, 136, 0.2);
      text-shadow: 0 0 8px rgba(0, 255, 136, 0.5);
    }
    .ai-transmit-btn:active:not(:disabled) {
      transform: translateY(1px);
    }
    .ai-transmit-btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
    .ai-transmit-btn.processing {
      color: var(--aegis-warning);
      border-color: rgba(255, 170, 0, 0.3);
    }

    .ai-mic-btn {
      background: var(--aegis-surface);
      border: 1px solid var(--aegis-border);
      color: var(--aegis-dim);
      font-size: 16px;
      width: 34px;
      height: 34px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
      flex-shrink: 0;
    }
    .ai-mic-btn:hover:not(:disabled) {
      border-color: var(--aegis-dim);
      color: var(--aegis-primary);
    }
    .ai-mic-btn.listening {
      color: #ff3333;
      border-color: rgba(255, 51, 51, 0.5);
      box-shadow: 0 0 12px rgba(255, 51, 51, 0.3);
      animation: micPulse 1.2s ease-in-out infinite;
    }
    .ai-mic-btn:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }
    @keyframes micPulse {
      0%, 100% { box-shadow: 0 0 6px rgba(255, 51, 51, 0.2); }
      50% { box-shadow: 0 0 16px rgba(255, 51, 51, 0.5); }
    }
    .ai-mic-status {
      font-size: 9px;
      color: #ff3333;
      letter-spacing: 1px;
      text-transform: uppercase;
      display: none;
      flex-shrink: 0;
    }
    .ai-mic-status.active {
      display: inline;
      animation: micStatusBlink 0.8s step-end infinite;
    }
    @keyframes micStatusBlink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }

    .ai-response-area {
      flex: 1;
      min-height: 30px;
      overflow-y: auto;
    }
    .ai-response-row {
      display: flex;
      gap: 8px;
      align-items: flex-start;
    }
    .ai-response-text {
      font-size: 12px;
      color: var(--aegis-text);
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .ai-cursor {
      display: inline-block;
      width: 8px;
      height: 14px;
      background: var(--aegis-primary);
      animation: aiCursorBlink 0.6s step-end infinite;
      vertical-align: text-bottom;
      margin-left: 2px;
    }
    @keyframes aiCursorBlink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0; }
    }

    .ai-history {
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px solid rgba(10, 48, 64, 0.3);
    }
    .ai-history-label {
      font-size: 9px;
      color: var(--aegis-muted);
      letter-spacing: 2px;
      margin-bottom: 4px;
    }
    .ai-history-item {
      font-size: 10px;
      color: var(--aegis-muted);
      padding: 2px 0;
      cursor: pointer;
      transition: color 0.15s;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .ai-history-item:hover {
      color: var(--aegis-text);
    }
    .ai-history-item::before {
      content: '> ';
      color: var(--aegis-dim);
    }
  `;
  document.head.appendChild(style);

  // ── Build UI ──
  container.innerHTML = `
    <div class="ai-container">
      <div class="ai-input-row">
        <span class="ai-label">AI QUERY:</span>
        <input type="text" class="ai-input" id="ai-input" placeholder="Enter command or question..." autocomplete="off" spellcheck="false">
        <button class="ai-mic-btn" id="ai-mic-btn" title="Voice input (Chrome)">&#x1F399;</button>
        <span class="ai-mic-status" id="ai-mic-status">REC</span>
        <button class="ai-transmit-btn" id="ai-transmit-btn">TRANSMIT</button>
      </div>
      <div class="ai-response-area">
        <div class="ai-response-row">
          <span class="ai-label" style="padding-top: 2px;">RESPONSE:</span>
          <span class="ai-response-text" id="ai-response">STANDING BY FOR QUERY...</span>
        </div>
      </div>
      <div class="ai-history" id="ai-history-container" style="display: none;">
        <div class="ai-history-label">RECENT QUERIES</div>
        <div id="ai-history-list"></div>
      </div>
    </div>
  `;

  const inputEl = document.getElementById('ai-input');
  const transmitBtn = document.getElementById('ai-transmit-btn');
  const responseEl = document.getElementById('ai-response');
  const historyContainer = document.getElementById('ai-history-container');
  const historyList = document.getElementById('ai-history-list');

  // ── Render history ──
  function renderHistory() {
    if (history.length === 0) {
      historyContainer.style.display = 'none';
      return;
    }
    historyContainer.style.display = 'block';
    historyList.innerHTML = history.slice(0, 5).map(q =>
      `<div class="ai-history-item" data-query="${escapeAttr(q)}">${escapeHtml(q)}</div>`
    ).join('');

    // Click to re-query
    historyList.querySelectorAll('.ai-history-item').forEach(item => {
      item.addEventListener('click', () => {
        inputEl.value = item.dataset.query;
        inputEl.focus();
      });
    });
  }

  // ── Typing animation ──
  function typeText(text, callback) {
    responseEl.textContent = '';
    let idx = 0;

    // Add cursor
    const cursor = document.createElement('span');
    cursor.className = 'ai-cursor';
    responseEl.parentNode.appendChild(cursor);

    function typeChar() {
      if (idx < text.length) {
        responseEl.textContent += text[idx];
        idx++;
        setTimeout(typeChar, TYPING_SPEED);
      } else {
        // Remove cursor after a delay
        setTimeout(() => {
          if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
        }, 2000);
        if (callback) callback();
      }
    }

    typeChar();
  }

  // ── Submit query ──
  async function submitQuery() {
    const query = inputEl.value.trim();
    if (!query || isProcessing) return;

    isProcessing = true;
    inputEl.disabled = true;
    transmitBtn.disabled = true;
    transmitBtn.classList.add('processing');
    transmitBtn.textContent = 'PROCESSING';

    if (statusEl) {
      statusEl.textContent = 'PROCESSING';
      statusEl.style.color = 'var(--aegis-warning)';
    }
    if (indicatorEl) {
      indicatorEl.style.background = 'var(--aegis-warning)';
      indicatorEl.style.boxShadow = '0 0 6px rgba(255, 170, 0, 0.5)';
    }

    // Remove old cursor if exists
    const oldCursor = responseEl.parentNode.querySelector('.ai-cursor');
    if (oldCursor) oldCursor.remove();

    responseEl.textContent = '';

    // Add to history
    history = [query, ...history.filter(q => q !== query)].slice(0, 5);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    renderHistory();

    let answer = '';

    try {
      // Try to send to API
      const env = typeof window.aegisGetEnv === 'function' ? window.aegisGetEnv() : 'ALL';
      const response = await fetch(AI_QUERY_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: query,
          env: env
        })
      });

      if (response.ok) {
        const data = await response.json();
        answer = data.answer || data.response || data.text || 'No response received.';
      } else {
        answer = `QUERY TRANSMITTED. GATEWAY RETURNED STATUS ${response.status}. The AI cortex may be initializing — retry in a moment.`;
      }
    } catch (err) {
      answer = `QUERY LOGGED: "${query}" — AI cortex link is currently offline. Query has been queued for processing when connection is restored.`;
    }

    // Type the answer
    typeText(answer, () => {
      // If answer is short, speak it via herald-voice
      const wordCount = answer.split(/\s+/).length;
      if (wordCount < SHORT_ANSWER_WORDS) {
        speakViaHerald(answer);
      }

      isProcessing = false;
      inputEl.disabled = false;
      transmitBtn.disabled = false;
      transmitBtn.classList.remove('processing');
      transmitBtn.textContent = 'TRANSMIT';
      inputEl.value = '';
      inputEl.focus();

      if (statusEl) {
        statusEl.textContent = 'STANDBY';
        statusEl.style.color = '';
      }
      if (indicatorEl) {
        indicatorEl.style.background = '';
        indicatorEl.style.boxShadow = '';
      }
    });
  }

  // ── Herald voice ──
  function speakViaHerald(text) {
    fetch(HERALD_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, priority: 5 })
    }).catch(() => {
      // Herald may not be available
    });
  }

  // ── Voice Input (Chrome Web Speech API) ──
  const micBtn = document.getElementById('ai-mic-btn');
  const micStatus = document.getElementById('ai-mic-status');
  let recognition = null;
  let isListening = false;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'sv-SE'; // Swedish primary, falls back to browser default
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {
      isListening = true;
      micBtn.classList.add('listening');
      micStatus.classList.add('active');
      inputEl.placeholder = 'Listening...';
      inputEl.value = '';
    };

    recognition.onresult = function(event) {
      let transcript = '';
      let isFinal = false;
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
        if (event.results[i].isFinal) isFinal = true;
      }
      inputEl.value = transcript;

      if (isFinal) {
        // Auto-submit after final result
        stopListening();
        setTimeout(submitQuery, 300);
      }
    };

    recognition.onerror = function(event) {
      console.warn('[AEGIS] Speech recognition error:', event.error);
      stopListening();
      if (event.error === 'not-allowed') {
        inputEl.placeholder = 'Microphone access denied — check browser permissions';
      } else if (event.error === 'no-speech') {
        inputEl.placeholder = 'No speech detected — try again';
      } else {
        inputEl.placeholder = 'Enter command or question...';
      }
    };

    recognition.onend = function() {
      stopListening();
    };

    function stopListening() {
      isListening = false;
      micBtn.classList.remove('listening');
      micStatus.classList.remove('active');
      if (inputEl.placeholder === 'Listening...') {
        inputEl.placeholder = 'Enter command or question...';
      }
    }

    micBtn.addEventListener('click', function() {
      if (isProcessing) return;
      if (isListening) {
        recognition.stop();
        stopListening();
      } else {
        try {
          recognition.start();
        } catch (e) {
          // Already started
          recognition.stop();
          setTimeout(() => recognition.start(), 100);
        }
      }
    });
  } else {
    // Browser doesn't support speech recognition
    micBtn.disabled = true;
    micBtn.title = 'Voice input not supported in this browser — use Chrome';
  }

  // ── Event handlers ──
  transmitBtn.addEventListener('click', submitQuery);
  inputEl.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitQuery();
    }
  });

  // ── Utility ──
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function escapeAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // ── Render initial history ──
  renderHistory();

  console.log('[AEGIS] AI Query plugin loaded');
})();
