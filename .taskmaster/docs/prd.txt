# AEGIS CONTROL — Mission Control PRD v4.0
**Codename:** AEGIS
**Platform:** Mac Mini (Minisomllhornss, user nss)
**AI Backend:** OpenAI API (gpt-4.1)
**TTS:** OpenAI TTS API — röst: `nova` (kvinna, auktoritativ, speed: 0.92)
**Nätverk:** OpenVPN per miljö + direkt för Cedervall
**Bygg-verktyg:** Claude Code (autonomt, ingen mänsklig godkänning mellan tasks)
**Style:** NASA ISS Mission Control · HAL 9000 female · Full drama

---

## Arkitekturbeslut — Hybrid Native + Docker

Docker Desktop på macOS kör i en Linux-VM. Det innebär tre hårda begränsningar:

1. `network_mode: host` når Mac:ens nätverk — inte VPN-tunnlar (tun0/tun1)
2. `afplay` finns inte i Linux-containers
3. `icmplib` ICMP ping kräver root/NET_RAW i containers

**Lösning: Hybrid-arkitektur**

| Tjänst | Körs som | Anledning |
|---|---|---|
| `orion-hub` | Native Python på Mac | Behöver nå VPN-tunnlar |
| `data-bridge` | Native Python på Mac | Behöver nå VPN-tunnlar + ICMP ping |
| `herald-voice` | Native Python på Mac | Behöver `afplay` (macOS) |
| `sentinel-eye` | Native Python på Mac | Anropar orion-hub lokalt |
| `openmct-ui` | Docker | Ren Node.js-webbserver, inget specialnätverk |

Alla native-processer hanteras av **`honcho`** (Procfile-baserad processhanterare).
`honcho` startas via `make dev`.

---

## Nätverksarkitektur

```
Mac Mini (AEGIS-host, 10.83.x.x Cedervall-nät)
  ├── Direkt              → Cedervall  (10.83.x.x)
  ├── OpenVPN tun0        → ValvX      (10.174.x.x)
  └── OpenVPN tun1        → GWSK       (192.168.100.x)

Native Python-processer ser alla tre nät direkt.
openmct-ui (Docker) pratar bara mot localhost:8001.
```

---

## Autonomt körningsläge

Claude Code kör ALLA tasks sekventiellt utan att vänta på mänsklig input.
Efter varje task körs VERIFY-loopen automatiskt.
Om verify misslyckas: fixa och kör verify igen. Max 3 försök per task.
Om task misslyckas 3 gånger: logga felet i `AEGIS_BUILD_LOG.md`, hoppa över
tasken, fortsätt med nästa, markera den misslyckade som BLOCKED.
Vid slutet: skriv komplett status i `AEGIS_BUILD_LOG.md`.

**Körordning:**
```
001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 009 → 010 → 011 → 012
```

---

## Miljökonfiguration

```env
# CEDERVALL (direkt nät)
ENV_CEDERVALL_WAZUH_URL=https://valvxwazuh01:9200
ENV_CEDERVALL_WAZUH_USER=
ENV_CEDERVALL_WAZUH_PASSWORD=
ENV_CEDERVALL_WINRM_HOST=
ENV_CEDERVALL_WINRM_USER=
ENV_CEDERVALL_WINRM_PASSWORD=
ENV_CEDERVALL_WINRM_DOMAIN=CEDERVALL
ENV_CEDERVALL_UNIFI_URL=https://10.83.0.1
ENV_CEDERVALL_UNIFI_KEY=

# VALVX (via OpenVPN tun0)
ENV_VALVX_WAZUH_URL=
ENV_VALVX_WAZUH_USER=
ENV_VALVX_WAZUH_PASSWORD=
ENV_VALVX_WINRM_HOST=10.174.120.101
ENV_VALVX_WINRM_USER=
ENV_VALVX_WINRM_PASSWORD=
ENV_VALVX_WINRM_DOMAIN=VALVX

# GWSK (via OpenVPN tun1)
ENV_GWSK_WINRM_HOST=192.168.100.3
ENV_GWSK_WINRM_USER=
ENV_GWSK_WINRM_PASSWORD=
ENV_GWSK_OPNSENSE_URL=https://192.168.100.254

# PERSONAL
ENV_PERSONAL_CRYPTOEDGE_HOST=172.16.170.22
ENV_PERSONAL_MBG6_HOST=172.16.170.186
ENV_PERSONAL_NEUROGENISYS_HOST=185.167.84.22

# OPENAI
OPENAI_API_KEY=

# KAMEROR (MAC-adress:Visningsnamn, kommaseparerat)
CAMERA_MAP=AABBCCDDEEFF:Serverrum,112233445566:Entré,FFEEDDCCBBAA:Kontor

# AEGIS
AEGIS_SECRET_KEY=
AEGIS_TIMEZONE=Europe/Stockholm
AEGIS_ORION_PORT=8001
AEGIS_HERALD_PORT=8002
AEGIS_UI_PORT=8080
```

---

## Röst-design

**API:** `POST https://api.openai.com/v1/audio/speech`
**Parametrar:** `model: tts-1`, `voice: nova`, `speed: 0.92`, `response_format: mp3`
**Cache:** `/tmp/aegis-voice/<sha256(text+voice+speed)>.mp3` — TTL 24h
**Uppspelning:** `subprocess.run(["afplay", "-v", "0.9", filepath])` — synkront i worker
**Kö:** `asyncio.Queue(maxsize=3)` — äldsta kastas om full

### Röstskript per händelse

| Händelse | Text |
|---|---|
| BOOT | "AEGIS Control online. All systems nominal. Awaiting operator input." |
| ENV-byte | "Switching to [ENV] environment. Loading telemetry." |
| SENSITIVE | "Attention. Personnel detected. Sensitive information protocols active." |
| INTRUSION | "Warning. Unauthorized access detected. Camera [NAMN]. Security breach in progress." |
| CRITICAL | "Critical alert. [title]. Immediate attention required." |
| WARNING 7–9 | "Advisory. [title]." |
| VPN nere | "Network anomaly. [ENV] environment unreachable. Attempting reconnection." |
| AI svar (<20 ord) | [svaret läses upp direkt] |
| SHUTDOWN | "AEGIS Control going offline. Goodbye." |

Alla fördefinierade fraser cachas vid startup (TASK-004).

---

## Repo-struktur

```
nsssthlm/aegis-control/
├── Procfile                    ← honcho: startar alla native-processer
├── Makefile
├── requirements.txt            ← gemensamma Python-beroenden
├── .env.example
├── .gitignore                  ← .env, __pycache__, *.mp3, aegis.db
├── AEGIS_BUILD_LOG.md          ← skapas av agenten
├── docker-compose.yml          ← bara openmct-ui
├── orion-hub/
│   ├── main.py
│   ├── config.py
│   ├── routers/
│   │   ├── websocket.py
│   │   ├── query.py
│   │   ├── webhook.py
│   │   └── status.py
│   └── services/
│       ├── ai_agent.py
│       ├── event_bus.py
│       └── database.py
├── data-bridge/
│   ├── main.py
│   └── collectors/
│       ├── wazuh.py
│       ├── winrm.py
│       ├── unifi.py
│       ├── ping.py
│       └── vpn_check.py
├── herald-voice/
│   └── main.py
├── sentinel-eye/
│   └── main.py
├── openmct-ui/
│   ├── Dockerfile
│   ├── package.json
│   ├── index.html
│   ├── main.js
│   └── plugins/
│       ├── aegis-theme/theme.js
│       ├── alert-feed/alert-feed.js
│       ├── server-grid/server-grid.js
│       ├── camera-presence/camera-presence.js
│       ├── ai-query/ai-query.js
│       ├── mission-overview/mission-overview.js
│       └── env-selector/env-selector.js
└── scripts/
    ├── smoke_test.sh
    ├── demo_alert.sh
    └── demo_presence.sh
```

---

## Python-beroenden (`requirements.txt`)

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
websockets==12.0
aiosqlite==0.20.0
httpx==0.27.0
python-dotenv==1.0.1
pywinrm[credssp]==0.4.3
icmplib==3.0.4
openai==1.30.0
honcho==1.1.0
```

**Viktigt:**
- `pywinrm[credssp]` — hakparenteserna är required för CredSSP-stöd
- `asyncio` ska INTE vara med — ingår i Python stdlib
- `icmplib` körs native på Mac, kräver inget root

---

## Procfile

```
orion-hub: uvicorn orion-hub.main:app --host 0.0.0.0 --port 8001 --reload
data-bridge: python3 -m data-bridge.main
herald-voice: uvicorn herald-voice.main:app --host 127.0.0.1 --port 8002
sentinel-eye: python3 -m sentinel-eye.main
```

---

## TASK-001: Repo, Procfile, Makefile, ENV-validering

**Vad:**
- Skapa komplett repo-struktur med alla mappar och tomma filer
- Skriva `Procfile` för honcho
- Skriva `docker-compose.yml` med ENBART `openmct-ui`
- Skriva `requirements.txt` (se ovan, inga avvikelser)
- Skriva `.env.example` med alla variabler
- Skriva `Makefile` med alla targets
- Skriva `config.py` i `orion-hub/` som validerar ENV vid startup

**`config.py` — required variabler (exit(1) om dessa saknas):**
```python
REQUIRED = [
    "OPENAI_API_KEY",
    "AEGIS_SECRET_KEY",
]
# Övriga variabler är optional (mjuk varning om de saknas)
```

**`docker-compose.yml` (ENBART openmct-ui):**
```yaml
services:
  openmct-ui:
    build: ./openmct-ui
    ports:
      - "8080:8080"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080"]
      interval: 10s
      timeout: 5s
      retries: 3
```

**Makefile:**
```makefile
.PHONY: dev stop logs test smoke demo-alert demo-presence voice-test build clean install

install:
	pip3 install -r requirements.txt
	docker compose build

dev:
	docker compose up -d
	honcho start
	# honcho blockerar — Ctrl+C stoppar alla processer

stop:
	docker compose down
	honcho stop 2>/dev/null || true

logs:
	honcho start 2>&1 | tee aegis.log

test:
	python3 -m pytest orion-hub/tests/ -v

smoke:
	@bash scripts/smoke_test.sh

demo-alert:
	@bash scripts/demo_alert.sh

demo-presence:
	@bash scripts/demo_presence.sh

voice-test:
	@curl -s -X POST http://localhost:8002/speak \
	  -H "Content-Type: application/json" \
	  -d '{"text":"AEGIS Control online. Voice system nominal. Ready for operations.","priority":10}'
	@echo "Voice test sent."

clean:
	docker compose down -v
	rm -f aegis.db
	rm -rf /tmp/aegis-voice/
```

### VERIFY TASK-001

```bash
# Steg 1: requirements installeras utan fel
pip3 install -r requirements.txt 2>&1 | grep -c "ERROR"
EXPECTED: 0

# Steg 2: honcho finns
which honcho
EXPECTED: en sökväg (t.ex. /usr/local/bin/honcho)

# Steg 3: pywinrm[credssp] korrekt installerat
python3 -c "import winrm; print('ok')"
EXPECTED: "ok"

# Steg 4: icmplib installerat
python3 -c "from icmplib import ping; print('ok')"
EXPECTED: "ok"

# Steg 5: docker compose bygger openmct-ui
docker compose build 2>&1 | grep -c "ERROR"
EXPECTED: 0

# Steg 6: .env ej i git
git ls-files .env 2>/dev/null
EXPECTED: tom output

# Steg 7: Procfile har alla fyra processer
grep -c ":" Procfile
EXPECTED: 4
```
**OM FEL pip:** `pip3 install --upgrade pip` sedan försök igen.
**OM FEL pywinrm:** kontrollera att hakparenteserna är med: `pip3 install 'pywinrm[credssp]'`

---

## TASK-002: orion-hub — FastAPI, WebSocket, Event Bus, SQLite

**Vad:**
Navet för all kommunikation. Kör native på Mac på port 8001.

**Event-schema:**
```json
{
  "id": "uuid4-sträng",
  "type": "SYSTEM|WAZUH|WINRM|UNIFI|PRESENCE|INTRUSION|SENSITIVE|PING|VPN|AI",
  "severity": "INFO|WARNING|CRITICAL|INTRUSION|SENSITIVE",
  "source": "hostname eller tjänstnamn",
  "env": "CEDERVALL|VALVX|GWSK|PERSONAL|ALL",
  "title": "max 80 tecken",
  "body": "max 500 tecken",
  "timestamp": "ISO8601 med timezone",
  "speak": false,
  "metadata": {}
}
```

**`main.py` startup-ordning:**
```python
# 1. config.py körs — validerar REQUIRED ENV, loggar saknade optional
# 2. SQLite initieras med WAL-mode och index
# 3. Event bus (asyncio) startar
# 4. HTTP + WebSocket-server startar på port 8001
# 5. SYSTEM-event broadcastas: title="AEGIS online", speak=True
```

**Endpoints:**
```
GET  /health
     → {"status":"operational","version":"4.0","uptime_seconds":N,"connected_clients":N}

WS   /ws
     → WebSocket, klienten får alla events broadcastade
     → Heartbeat: skicka {"type":"PING"} var 30s, förvänta {"type":"PONG"}
     → Om klient ej svarar på 3 pings: stäng anslutning

POST /api/internal/event
     → tar emot Event-schema från data-bridge/sentinel-eye
     → sparar i SQLite
     → broadcastar till alla WS-klienter
     → om speak=True: POST http://localhost:8002/speak {text: rösttext}
     → returnerar {"id": "uuid"}

POST /api/webhook
     → tar emot UniFi Protect POST
     → vidarebefordrar rå payload till sentinel-eye: POST http://localhost:8003/process
     → returnerar 200 omedelbart (< 100ms)

POST /api/query
     Body: {"question": "string", "env": "CEDERVALL|ALL|..."}
     → injicerar kontext (senaste 10 events + status summary)
     → anropar OpenAI gpt-4.1
     → returnerar {"answer": "string", "tokens_used": N}

GET  /api/events
     Query params: env=, severity=, limit=50, offset=0
     → returnerar array av events från SQLite, nyaste först

GET  /api/status/summary
     → returnerar aggregerad status per miljö:
     {
       "CEDERVALL": {"status":"ok|degraded|unreachable","alerts_24h":N,
                     "threat_level":"GREEN|YELLOW|ORANGE|RED|BLACK",
                     "last_event":"ISO8601","servers":{...}},
       "VALVX": {...},
       "GWSK": {...},
       "PERSONAL": {...}
     }
```

**`database.py`:**
```python
# SQLite-fil: aegis.db (projektrot)
# WAL-mode: PRAGMA journal_mode=WAL
#
# Tabell events:
#   id TEXT PRIMARY KEY,
#   type TEXT, severity TEXT, source TEXT, env TEXT,
#   title TEXT, body TEXT, timestamp TEXT,
#   speak INTEGER, metadata TEXT (JSON)
#
# Tabell ai_context:
#   event_id TEXT PRIMARY KEY,
#   analysis TEXT, created_at TEXT
#
# Index: idx_events_timestamp, idx_events_severity, idx_events_env
# Auto-rensning vid startup: DELETE FROM events WHERE timestamp < now - 7 dagar
```

**`ai_agent.py`:**
```python
# Modell: gpt-4.1
# Max tokens svar: 150
# Timeout: 8 sekunder
# System prompt (exakt):
SYSTEM_PROMPT = """You are AEGIS — the mission control AI for Omneforge IT infrastructure.
You are authoritative, precise and calm like an ISS flight director.
You respond in maximum three sentences. Never express uncertainty — if data is unavailable, say "Data unavailable."
You refer to servers by their actual names. You respond in the same language as the question.
Current context will be injected with each query."""

# Kontext-injection per query:
# f"Active environment: {env}\n"
# f"Last 10 events:\n{events_summary}\n"
# f"System status:\n{status_summary}"
#
# Om OpenAI timeout: returnera {"answer": "Data unavailable. Check Orion Hub.", "tokens_used": 0}
# Om OpenAI 429 (rate limit): vänta 5s, försök en gång till
```

**`event_bus.py`:**
```python
# asyncio.Queue för inkommande events
# Set av aktiva WebSocket-klienter
# Broadcast till alla klienter inom 500ms
# Om klient stängt anslutning: ta bort ur set utan krasch
```

### VERIFY TASK-002

```bash
# Steg 1: starta orion-hub isolerat
cd orion-hub && uvicorn main:app --port 8001 &
sleep 3

# Steg 2: health
curl -s http://localhost:8001/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])"
EXPECTED: operational

# Steg 3: intern event
curl -s -X POST http://localhost:8001/api/internal/event \
  -H "Content-Type: application/json" \
  -d '{"id":"test-001","type":"SYSTEM","severity":"INFO","source":"verify",
       "env":"ALL","title":"VERIFY","body":"","timestamp":"2025-01-01T00:00:00Z",
       "speak":false,"metadata":{}}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('id') else 'fail')"
EXPECTED: ok

# Steg 4: events hämtbara
curl -s "http://localhost:8001/api/events?limit=1" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if len(d)>0 else 'empty')"
EXPECTED: ok

# Steg 5: WebSocket tar emot event
python3 -c "
import asyncio, websockets, json
async def t():
    async with websockets.connect('ws://localhost:8001/ws') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        d = json.loads(msg)
        print(d.get('type','unknown'))
asyncio.run(t())
"
EXPECTED: SYSTEM

# Steg 6: AI query (kräver OPENAI_API_KEY i .env)
curl -s -X POST http://localhost:8001/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"status check","env":"ALL"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if len(d.get('answer',''))>5 else 'fail')"
EXPECTED: ok

# Steg 7: stoppa orion-hub
kill %1 2>/dev/null
```
**OM FEL:** `docker logs` finns inte här — kör `cat aegis.log` eller kör processen
direkt i terminalen för att se stack trace.

---

## TASK-003: Open MCT UI — ISS-estetik och boot-sekvens

**Vad:**
NASA Open MCT med custom plugins och full ISS-visuell design. Kör i Docker.

**Installation:**
```bash
# I openmct-ui/
git clone https://github.com/nasa/openmct.git .
npm install
# Skapa sedan custom index.html och plugins
```

**Dockerfile:**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
EXPOSE 8080
CMD ["node", "server.js"]
```

**CSS-tema (`aegis-theme/theme.js`):**
```css
:root {
  --aegis-bg:        #020c0e;
  --aegis-surface:   #041418;
  --aegis-border:    #0a3040;
  --aegis-primary:   #00ff88;
  --aegis-dim:       #007744;
  --aegis-warning:   #ffaa00;
  --aegis-critical:  #ff3333;
  --aegis-intrusion: #ff0066;
  --aegis-sensitive: #ff6600;
  --aegis-text:      #b0ffd0;
  --aegis-muted:     #446655;
  --aegis-font:      'Space Mono', 'Courier New', monospace;
}

/* Scanlines */
body::after {
  content: '';
  position: fixed;
  inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,0,0,0.12) 2px, rgba(0,0,0,0.12) 4px
  );
  pointer-events: none;
  z-index: 9999;
}
```

**Boot-sekvens (index.html — visas 4 sekunder):**
```
# Svart bakgrund, grön Space Mono-text rullar snabbt:

AEGIS CONTROL SYSTEM v4.0
OMNEFORGE OPERATIONS CENTER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INITIALIZING SUBSYSTEMS...
  [■■■■■■■■] EVENT BUS ............... OK
  [■■■■■■■■] TELEMETRY COLLECTOR ..... OK
  [■■■■■■■■] CAMERA SENTINEL ......... OK
  [■■■■■■■■] VOICE HERALD ............ OK
  [■■■■■■■■] AI INTELLIGENCE ......... OK
CONNECTING TO ORION HUB... CONNECTED
LOADING MISSION PROFILE...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL SYSTEMS NOMINAL

# Fade in till normal UI efter 4 sekunder
# herald-voice POST: "AEGIS Control online. All systems nominal. Awaiting operator input."
```

**Layout — sex paneler:**
```
┌──────────────────────────────────────────────────────────────────┐
│  AEGIS CONTROL          [ENV: CEDERVALL ▼]           14:32 UTC  │
│  ● CONNECTED  ◆ AI:ONLINE  ▲ THREAT: GREEN  ■ NSS              │
├──────────────────┬───────────────────────────────────────────────┤
│  MISSION OVERVIEW│  ALERT FEED                                   │
│  (alla miljöer)  │  (live events, scrollar)                      │
├──────────────────┼───────────────────────────────────────────────┤
│  SYSTEM STATUS   │  CAMERA PRESENCE                              │
│  (server-grid)   │  (kameror + presence-overlay)                 │
├──────────────────┴───────────────────────────────────────────────┤
│  AI QUERY: [_________________________________]      [TRANSMIT]   │
│  RESPONSE: [typing-animation här]                               │
└──────────────────────────────────────────────────────────────────┘
```

**WebSocket-klient (main.js):**
```javascript
// Ansluter till ws://localhost:8001/ws
// Reconnect med exponentiell backoff: 1s, 2s, 4s, 8s, max 30s
// Vid disconnect: statusbar visar "● RECONNECTING..."
// Vid reconnect: statusbar visar "● CONNECTED"
// Svarar på {"type":"PING"} med {"type":"PONG"}
// Alla inkommande events routas till rätt plugin via CustomEvent
```

**Alert Feed (`alert-feed.js`):**
```javascript
// Max 100 events i listan (äldsta tas bort)
// Ny event: slide in från toppen med CSS animation
// Färgkodning vänsterbård:
//   INFO:      #00ff88
//   WARNING:   #ffaa00
//   CRITICAL:  #ff3333 + puls-animation
//   INTRUSION: #ff0066 + hela raden blinkar 3 gånger
//   SENSITIVE: #ff6600
// AI-analys (om finns): visas som grå kursiv text under alertsen
// ENV-filter: om vald ENV != ALL, visa bara events för vald ENV + ALL
```

**ENV-selector (`env-selector.js`):**
```javascript
// Dropdown: CEDERVALL / VALVX / GWSK / PERSONAL / ALL
// Vid byte:
//   1. Filtrera Alert Feed, Server Grid, Camera Presence
//   2. POST http://localhost:8002/speak {"text": "Switching to [ENV] environment."}
//   3. Spara i localStorage("aegis-env")
// Läs localStorage vid sidladdning
```

**Threat Level-logik (`main.js`):**
```javascript
// Beräknas från events i Alert Feed senaste 30 minuter:
// GREEN:  inga WARNING/CRITICAL/INTRUSION
// YELLOW: minst ett WARNING
// ORANGE: minst ett CRITICAL
// RED:    minst ett INTRUSION
// BLACK:  multipla INTRUSION eller orion-hub disconnected > 60s
// Visas i header med rätt bakgrundsfärg
```

### VERIFY TASK-003

```bash
# Steg 1: Docker-image bygger
docker compose build openmct-ui 2>&1 | grep -c "ERROR"
EXPECTED: 0

# Steg 2: container startar och svarar
docker compose up -d openmct-ui
sleep 10
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080
EXPECTED: 200

# Steg 3: AEGIS finns i HTML
curl -s http://localhost:8080 | grep -c "AEGIS"
EXPECTED: minst 1

# Steg 4: Space Mono-font refereras
curl -s http://localhost:8080 | grep -c "Space Mono"
EXPECTED: minst 1

# Steg 5: ENV-selector finns
curl -s http://localhost:8080 | grep -c "CEDERVALL"
EXPECTED: minst 1

# Steg 6: skicka event och verifiera UI (manuell kontroll)
# Öppna http://localhost:8080 i Chrome
# Kör: curl -X POST http://localhost:8001/api/internal/event \
#   -d '{"id":"ui-test","type":"WAZUH","severity":"WARNING","source":"test",
#        "env":"ALL","title":"UI VERIFY TEST","body":"","timestamp":"2025-01-01T00:00:00Z",
#        "speak":false,"metadata":{}}'
# Alert Feed ska visa "UI VERIFY TEST" inom 3 sekunder
EXPECTED: event synligt med gul vänsterbård
```

---

## TASK-004: herald-voice — TTS med OpenAI nova

**Vad:**
TTS-tjänst, kör native på Mac på port 8002. Använder `afplay` för uppspelning.

**`herald-voice/main.py` — komplett specifikation:**
```python
# FastAPI på port 8002 (localhost only)
#
# POST /speak
#   Body: {"text": str, "priority": int = 5}
#   → cache-nyckel = sha256(text + "nova" + "0.92")
#   → om cache miss: anropa OpenAI TTS API, spara MP3
#   → lägg i asyncio.Queue(maxsize=3)
#   → äldsta kastas om kön är full (ej låg-prioritet)
#   → returnerar {"queued": true, "cached": bool} OMEDELBART
#
# GET /health
#   → {"status":"operational","queue_size":N,"cache_files":N}
#
# Worker coroutine (kör parallellt med HTTP-server):
#   while True:
#     text, filepath = await queue.get()
#     subprocess.run(["afplay", "-v", "0.9", filepath], check=False)
#     await asyncio.sleep(0.1)
#
# Cache-mapp: /tmp/aegis-voice/ (skapas vid startup om saknas)
# Cache TTL: ta bort filer äldre än 24h vid startup
#
# OpenAI TTS-anrop:
#   client = openai.OpenAI()
#   response = client.audio.speech.create(
#       model="tts-1",
#       voice="nova",
#       input=text,
#       speed=0.92,
#       response_format="mp3"
#   )
#   response.stream_to_file(filepath)
#
# Fördefinierade fraser cachas vid startup (9 stycken från röst-design-tabellen)
# Startup-logik:
#   1. Skapa /tmp/aegis-voice/ om saknas
#   2. Rensa filer > 24h
#   3. Generera och cachas alla fördefinierade fraser
#   4. Starta worker
#   5. Starta HTTP-server
```

### VERIFY TASK-004

```bash
# Steg 1: starta herald-voice isolerat
cd herald-voice && uvicorn main:app --host 127.0.0.1 --port 8002 &
sleep 5

# Steg 2: health
curl -s http://localhost:8002/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])"
EXPECTED: operational

# Steg 3: cache skapades vid startup
curl -s http://localhost:8002/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d['cache_files']>=9 else d['cache_files'])"
EXPECTED: ok

# Steg 4: rösttest (HÖRS UR HÖGTALARE — kontrollera manuellt)
curl -s -X POST http://localhost:8002/speak \
  -H "Content-Type: application/json" \
  -d '{"text":"AEGIS voice verification complete. System nominal.","priority":10}'
sleep 5
echo "Hördes rösten? (manuell kontroll)"

# Steg 5: MP3-fil skapades
ls /tmp/aegis-voice/*.mp3 | wc -l
EXPECTED: minst 10 (9 fördefinierade + 1 ny)

# Steg 6: kö-throttling
for i in 1 2 3 4 5; do
  curl -s -X POST http://localhost:8002/speak \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"Test meddelande $i\",\"priority\":5}" &
done
wait
sleep 1
curl -s http://localhost:8002/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d['queue_size']<=3 else d['queue_size'])"
EXPECTED: ok

kill %1 2>/dev/null
```
**OM FEL afplay:** kör `which afplay` — ska ge `/usr/bin/afplay`.
Kör INTE i Docker, måste vara native.

---

## TASK-005: data-bridge — Wazuh Integration

**Vad:**
Poller mot Wazuh Indexer (OpenSearch). Kör native på Mac.

**`collectors/wazuh.py`:**
```python
# Klass WazuhCollector(env: str, config: dict)
#
# Poll-intervall: 15 sekunder
# HTTP-klient: httpx.AsyncClient(verify=False, timeout=10)
#   (verify=False för Wazuh self-signed cert — logga varning vid startup)
#
# Query:
# POST https://<url>:9200/wazuh-alerts-4.x-*/_search
# Auth: httpx.BasicAuth(user, password)
# Body:
# {
#   "query": {"range": {"rule.level": {"gte": 7}}},
#   "sort": [{"@timestamp": {"order": "desc"}}],
#   "size": 50,
#   "_source": ["rule.level","rule.description","agent.name",
#               "agent.ip","@timestamp","rule.groups"]
# }
#
# Deduplicering: self.seen_ids = set() — max 1000 entries (LRU-liknande: ta bort äldsta 100 om > 1000)
#
# Severity-mappning:
#   level 7-9:  severity=WARNING,  speak=False
#   level 10-11: severity=CRITICAL, speak=True
#   level 12+:  severity=CRITICAL, speak=True
#
# Rösttext för speak=True:
#   level 10-11: f"Advisory. {rule_description[:60]}"
#   level 12+:   f"Critical alert. {rule_description[:60]}. Immediate attention required."
#
# POST till orion-hub: http://localhost:8001/api/internal/event
#
# Felhantering (circuit breaker):
#   self.fail_count = 0
#   Vid ConnectionError/Timeout: fail_count += 1, vänta 30s
#   Om fail_count >= 5: skicka VPN-event till orion-hub, vänta 60s, reset fail_count
#   Vid 401: logga "Wazuh auth failed [{env}]", vänta 60s (försök ej oftare)
#   Vid succé: fail_count = 0
```

**`data-bridge/main.py`:**
```python
# Startar collectors för alla konfigurerade miljöer
# Varje collector kör som asyncio-task
# Om en collector kraschar: logga, vänta 10s, starta om
# Status-endpoint: GET http://localhost:8004/status (intern monitoring)
```

### VERIFY TASK-005

```bash
# Steg 1: data-bridge startar
python3 -m data-bridge.main &
sleep 5

# Steg 2: inga EXCEPTION i output
# (kontrollera terminalfönstret)

# Steg 3: wazuh-status i summary
curl -s http://localhost:8001/api/status/summary | python3 -c "
import sys,json; d=json.load(sys.stdin)
c = d.get('CEDERVALL',{}).get('wazuh',{})
print('connected:', c.get('connected','missing'))
print('last_poll:', 'ok' if c.get('last_poll') else 'missing')
"
EXPECTED:
connected: True (eller False om Wazuh ej nåbar)
last_poll: ok

# Steg 4: deduplicerings-test
python3 -c "
from data_bridge.collectors.wazuh import WazuhCollector
c = WazuhCollector('test', {})
c.seen_ids.add('dup-id-001')
print('dup' if 'dup-id-001' in c.seen_ids else 'fail')
"
EXPECTED: dup

# Steg 5: LRU-begränsning
python3 -c "
from data_bridge.collectors.wazuh import WazuhCollector
c = WazuhCollector('test', {})
for i in range(1100):
    c.seen_ids.add(f'id-{i}')
    if len(c.seen_ids) > 1000:
        oldest = list(c.seen_ids)[:100]
        for old in oldest:
            c.seen_ids.discard(old)
print('ok' if len(c.seen_ids) <= 1000 else len(c.seen_ids))
"
EXPECTED: ok

kill %1 2>/dev/null
```

---

## TASK-006: data-bridge — Windows Event Log via WinRM

**`collectors/winrm.py`:**
```python
# Klass WinRMCollector(env: str, config: dict)
# Bibliotek: winrm (pywinrm[credssp])
#
# Poll-intervall: 30 sekunder
# Timeout per WinRM-anrop: 10 sekunder
# Auth: CredSSP
#
# PowerShell som körs:
PS_QUERY = """
$cutoff = (Get-Date).AddSeconds(-35)
try {
    $events = Get-WinEvent -FilterHashtable @{
        LogName='Security','System';
        Id=4625,4648,7045,1102,4740,4776;
        StartTime=$cutoff
    } -ErrorAction SilentlyContinue
    if ($events) { $events | Select-Object Id,TimeCreated,
        @{N='Message';E={$_.Message.Substring(0,[Math]::Min(300,$_.Message.Length))}},
        @{N='SubjectUser';E={$_.Properties[5].Value}} |
        ConvertTo-Json -Depth 2 -Compress
    } else { '[]' }
} catch { '[]' }
"""
#
# Event-mappning:
EVENT_MAP = {
    4625: ("WARNING",  "Failed logon attempt",        False),
    4648: ("WARNING",  "Explicit credential use",     False),
    7045: ("CRITICAL", "New service installed",       True),
    1102: ("CRITICAL", "AUDIT LOG CLEARED",           True),
    4740: ("WARNING",  "Account locked out",          False),
    4776: ("INFO",     "NTLM authentication attempt", False),
}
#
# Brute force detection:
#   self.failed_logons = {}  # {source_ip: [timestamps]}
#   Om 5+ 4625-events från samma IP inom 60s:
#     → CRITICAL event: "Brute force attack from {ip} — {count} attempts"
#     → speak=True, text: "Critical alert. Brute force attack detected."
#     → rensa listan för den IP:n
#
# Felhantering:
#   WinRM timeout:  logga, fail_count++, vänta 30s
#   AuthError:      logga "WinRM auth failed [{env}]", vänta 60s
#   fail_count >= 5: markera host som UNREACHABLE, skicka VPN-check-event
```

### VERIFY TASK-006

```bash
# Steg 1: WinRM-modul importerar korrekt
python3 -c "
from data_bridge.collectors.winrm import WinRMCollector
print('import ok')
"
EXPECTED: import ok

# Steg 2: CredSSP-stöd finns
python3 -c "
import winrm
t = winrm.transport.Transport(endpoint='test', auth_method='credssp', username='x', password='x')
print('credssp ok')
"
EXPECTED: credssp ok (ingen ImportError)

# Steg 3: brute force-detektion — enhetstest
python3 -c "
from data_bridge.collectors.winrm import WinRMCollector
import time
c = WinRMCollector('test', {})
ip = '1.2.3.4'
ts = time.time()
for i in range(6):
    c.failed_logons.setdefault(ip, []).append(ts)
triggered = len(c.failed_logons.get(ip,[])) >= 5
print('ok' if triggered else 'fail')
"
EXPECTED: ok

# Steg 4: status summary inkluderar winrm
curl -s http://localhost:8001/api/status/summary | python3 -c "
import sys,json; d=json.load(sys.stdin)
c = d.get('CEDERVALL',{}).get('winrm',{})
print('ok' if 'connected' in c else 'missing')
"
EXPECTED: ok
```

---

## TASK-007: data-bridge — UniFi + Ping + VPN-check

**`collectors/ping.py`:**
```python
# Klass PingCollector(targets: dict)
# Bibliotek: icmplib
# from icmplib import ping as icmp_ping
#
# Kör native på Mac — inget root-krav
# Intervall: 30 sekunder
#
# Per host:
#   host = icmp_ping(ip, count=3, interval=0.5, timeout=3, privileged=False)
#   online = host.is_alive
#
# State tracking per host:
#   self.state = {}  # {"CV-DC05": {"online": True, "fail_count": 0}}
#
# Händelser:
#   online → offline (1 gång): WARNING event, speak=False
#   offline (3 gånger i rad): CRITICAL event, speak=True
#     text: "Critical alert. Host {name} is unreachable."
#   offline → online: INFO event "Host {name} back online", speak=False
#
# Uppdaterar status summary (skickas till orion-hub som PING-event)
```

**`collectors/vpn_check.py`:**
```python
# Kontrollerar var 60:e sekund om VPN-tunnlar är uppe
# import subprocess
# result = subprocess.run(["ifconfig", "tun0"], capture_output=True, text=True)
# tun0_up = result.returncode == 0 and "inet " in result.stdout
#
# Om tun0 var uppe och nu nere:
#   → WARNING event: "VPN tun0 (ValvX) disconnected"
#   → speak=True: "Network anomaly. ValvX environment unreachable."
#   → Markera VALVX som UNREACHABLE i status
#
# Samma för tun1 (GWSK)
# Om tun0/tun1 aldrig var uppe: logga en gång "VPN tun0 not configured", gör inget mer
```

**`collectors/unifi.py`:**
```python
# UniFi Network API
# Auth: headers={"X-API-KEY": key}
# SSL: verify=False (UniFi self-signed cert)
# Intervall: 30 sekunder
# Timeout: 5 sekunder
#
# Endpoints som pollas:
#   /proxy/network/integration/v1/sites/default/clients
#   /proxy/network/integration/v1/sites/default/devices
#
# Skickar INFO-events med metrics (speak=False)
# WAN down → CRITICAL omedelbart (speak=True)
#   text: "Critical alert. WAN connectivity lost."
```

### VERIFY TASK-007

```bash
# Steg 1: ping utan root
python3 -c "
from icmplib import ping
h = ping('127.0.0.1', count=1, timeout=2, privileged=False)
print('ok' if h.is_alive else 'fail')
"
EXPECTED: ok

# Steg 2: localhost är online i status
sleep 35  # vänta en poll-cykel
curl -s http://localhost:8001/api/status/summary | python3 -c "
import sys,json; d=json.load(sys.stdin)
servers = []
for env in d.values():
    servers.extend(env.get('servers',{}).values())
online = [s for s in servers if s.get('status')=='online']
print(f'online hosts: {len(online)}')
"
EXPECTED: online hosts: minst 1

# Steg 3: vpn_check importerar
python3 -c "from data_bridge.collectors.vpn_check import VpnChecker; print('ok')"
EXPECTED: ok
```

---

## TASK-008: sentinel-eye — UniFi Presence Detection

**`sentinel-eye/main.py`:**
```python
# FastAPI på port 8003 (localhost only)
#
# POST /process
#   Body: rå UniFi Protect webhook-payload
#   → parsa payload
#   → kör presence-logik
#   → POST till orion-hub /api/internal/event
#   → returnerar 200 omedelbart
#
# Presence-logik:
from zoneinfo import ZoneInfo
STOCKHOLM = ZoneInfo("Europe/Stockholm")

def classify_presence(payload: dict) -> dict:
    triggers = payload.get("alarm", {}).get("triggers", [])
    if not triggers or triggers[0].get("key") != "person":
        return None  # ignorera non-person events

    device_mac = triggers[0].get("device", "UNKNOWN")
    camera_name = CAMERA_MAP.get(device_mac, device_mac)

    now = datetime.now(tz=STOCKHOLM)
    is_workhours = (now.weekday() < 5 and 8 <= now.hour < 18)

    if is_workhours:
        return {
            "type": "SENSITIVE",
            "severity": "SENSITIVE",
            "title": f"Personnel detected — {camera_name}",
            "speak_text": "Attention. Personnel detected. Sensitive information protocols active."
        }
    else:
        return {
            "type": "INTRUSION",
            "severity": "INTRUSION",
            "title": f"INTRUSION DETECTED — {camera_name}",
            "speak_text": f"Warning. Unauthorized access detected. Camera {camera_name}. Security breach in progress."
        }
#
# Throttling per kamera:
#   self.last_event = {}  # {device_mac: timestamp}
#   Om senaste event < 60 sekunder sedan: ignorera
#
# CAMERA_MAP läses från ENV CAMERA_MAP:
#   "AABB:Serverrum,CCDD:Entré" → {"AABB": "Serverrum", "CCDD": "Entré"}
```

**README-sektion: UniFi Protect Alarm Manager Setup:**
```
Gör detta en gång i UniFi Protect:

1. Protect → Alarm Manager → Create Alarm
2. Name: "AEGIS Arbetstid"
   Trigger: Person detection
   Scope: ALLA kameror
   Schedule: Måndag–Fredag 08:00–18:00
   Action → Custom Webhook
   Method: POST
   URL: http://[MAC_MINI_IP]:8001/api/webhook
   Ignore repeated actions: 60 seconds
   → Save

3. Create Alarm
   Name: "AEGIS After Hours"
   Trigger: Person detection
   Scope: ALLA kameror
   Schedule: Alla tider UTOM måndag–fredag 08:00–18:00
   Action → Custom Webhook (samma URL)
   Ignore repeated actions: 60 seconds
   → Save

Lägg till kamerornas MAC-adresser i .env:
CAMERA_MAP=F4E2C60E6104:Serverrum,AABBCC112233:Entré
```

### VERIFY TASK-008

```bash
# Steg 1: sentinel-eye startar
python3 -m sentinel-eye.main &
sleep 3

# Steg 2: simulera person-detection webhook
curl -s -X POST http://localhost:8001/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alarm": {
      "name": "AEGIS Test",
      "sources": [{"device": "AABBCCDDEEFF", "type": "include"}],
      "triggers": [{"key": "person", "device": "AABBCCDDEEFF"}]
    },
    "timestamp": '"$(python3 -c 'import time; print(int(time.time()))')"'
  }' | python3 -c "import sys; print('ok' if '200' in sys.stdin.read() or True else 'fail')"
# (alltid 200 eftersom orion-hub svarar omedelbart)
sleep 3

# Steg 3: event skapades
curl -s "http://localhost:8001/api/events?limit=5" | python3 -c "
import sys,json; events=json.load(sys.stdin)
found = [e for e in events if e['type'] in ('SENSITIVE','INTRUSION')]
print('ok' if found else 'no presence event found')
"
EXPECTED: ok

# Steg 4: throttling (skicka samma direkt igen)
curl -s -X POST http://localhost:8001/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"alarm":{"name":"t","sources":[{"device":"AABBCCDDEEFF","type":"include"}],"triggers":[{"key":"person","device":"AABBCCDDEEFF"}]},"timestamp":1}'
sleep 2
curl -s "http://localhost:8001/api/events?limit=10" | python3 -c "
import sys,json; events=json.load(sys.stdin)
found = [e for e in events if e['type'] in ('SENSITIVE','INTRUSION')]
print('throttled' if len(found)==1 else f'not throttled: {len(found)} events')
"
EXPECTED: throttled

kill %1 2>/dev/null
```

---

## TASK-009: AI Query Panel och Alert Contextualization

**`plugins/ai-query/ai-query.js`:**
```javascript
// Layout (se TASK-003 för placering)
// Enter eller klick på TRANSMIT skickar frågan
//
// Skicka:
// fetch('http://localhost:8001/api/query', {
//   method: 'POST',
//   headers: {'Content-Type': 'application/json'},
//   body: JSON.stringify({question: input.value, env: currentEnv})
// })
//
// Typing-animation:
//   Rensa svar-div
//   Visa cursor "█" som blinkar
//   Lägg till ett tecken var 25ms
//   När klar: ta bort cursor
//
// Om svar < 20 ord: POST http://localhost:8002/speak {text: answer}
//
// Historik: senaste 5 frågor i sessionStorage
//   Format: [{question, answer, timestamp}, ...]
//
// Felhantering:
//   fetch timeout 10s: visa "DATA UNAVAILABLE. CONTACT GROUND CONTROL."
//   HTTP !ok:          visa "ORION HUB OFFLINE."
```

**Alert Contextualization (`ai_agent.py` tillägg):**
```python
# Lyssna på event_bus för severity == CRITICAL
# Per CRITICAL event:
#   1. Kolla SQLite ai_context: om event_id redan finns → hoppa över
#   2. Skapa OpenAI-anrop:
prompt = f"""You are AEGIS. Describe this security event in exactly 2 sentences.
What does it mean and what should the operator check next?
Event: {event.title}
Source: {event.source}
Environment: {event.env}
Body: {event.body[:200]}"""
#   3. gpt-4.1, max_tokens=80, timeout=8s
#   4. Spara i ai_context(event_id, analysis)
#   5. Broadcastas som nytt event:
#      type=AI, severity=INFO, env=event.env,
#      title=f"AI analysis: {event.title[:50]}",
#      body=analysis, speak=False
#   6. Vid OpenAI fel: logga tyst, gör ingenting (ej felmeddelande i UI)
```

### VERIFY TASK-009

```bash
# Steg 1: AI query returnerar svar
curl -s -X POST http://localhost:8001/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the status of all servers?","env":"ALL"}' \
  | python3 -c "
import sys,json; d=json.load(sys.stdin)
answer = d.get('answer','')
print('ok' if len(answer) > 10 else f'too short: {repr(answer)}')
"
EXPECTED: ok

# Steg 2: contextualization triggas av CRITICAL
curl -s -X POST http://localhost:8001/api/internal/event \
  -H "Content-Type: application/json" \
  -d '{
    "id":"ctx-test-001",
    "type":"WINRM","severity":"CRITICAL","source":"CV-DC05",
    "env":"CEDERVALL","title":"Audit log cleared by Administrator",
    "body":"EventID 1102","timestamp":"2025-01-01T00:00:00Z",
    "speak":true,"metadata":{}
  }'
sleep 12

curl -s "http://localhost:8001/api/events?limit=20" | python3 -c "
import sys,json; events=json.load(sys.stdin)
ai = [e for e in events if e['type']=='AI']
print('ok' if ai else 'no AI analysis generated')
"
EXPECTED: ok

# Steg 3: deduplicering (skicka samma event igen)
curl -s -X POST http://localhost:8001/api/internal/event \
  -H "Content-Type: application/json" \
  -d '{
    "id":"ctx-test-001",
    "type":"WINRM","severity":"CRITICAL","source":"CV-DC05",
    "env":"CEDERVALL","title":"Audit log cleared by Administrator",
    "body":"EventID 1102","timestamp":"2025-01-01T00:00:01Z",
    "speak":false,"metadata":{}
  }'
sleep 8
curl -s "http://localhost:8001/api/events?limit=30" | python3 -c "
import sys,json; events=json.load(sys.stdin)
ai = [e for e in events if e['type']=='AI']
print('ok (deduped)' if len(ai)==1 else f'not deduped: {len(ai)} AI events')
"
EXPECTED: ok (deduped)
```

---

## TASK-010: Mission Overview Panel

**`plugins/mission-overview/mission-overview.js`:**
```javascript
// Pollar GET /api/status/summary var 30:e sekund
// Renderar tabell med en rad per miljö:
//   ENV | STATUS | ALERTS 24H | THREAT LEVEL | LAST EVENT
//
// STATUS-färger:
//   ok:          grön text + "● OK"
//   degraded:    gul text  + "◐ DEGRADED"
//   unreachable: röd text  + "○ UNREACHABLE"
//
// Klick på rad: sätt ENV-selector till den miljön
//   dispatch CustomEvent('aegis-env-change', {detail: {env: 'CEDERVALL'}})
//
// Panelen är alltid synlig oavsett vald ENV
// Uppdaterar Threat Level per miljö i bakgrunden
```

### VERIFY TASK-010

```bash
# Steg 1: summary returnerar alla fyra miljöer
curl -s http://localhost:8001/api/status/summary | python3 -c "
import sys,json; d=json.load(sys.stdin)
envs = set(d.keys())
expected = {'CEDERVALL','VALVX','GWSK','PERSONAL'}
missing = expected - envs
print('ok' if not missing else f'missing: {missing}')
"
EXPECTED: ok

# Steg 2: varje miljö har rätt struktur
curl -s http://localhost:8001/api/status/summary | python3 -c "
import sys,json; d=json.load(sys.stdin)
for env, data in d.items():
    required = {'status','alerts_24h','threat_level','last_event','servers'}
    missing = required - set(data.keys())
    if missing:
        print(f'{env} saknar: {missing}')
    else:
        print(f'{env}: ok')
"
EXPECTED: fyra rader med "ok"

# Steg 3: panelen finns i HTML
curl -s http://localhost:8080 | grep -c "MISSION OVERVIEW"
EXPECTED: minst 1
```

---

## TASK-011: Demo-scripts och Smoke Test

**`scripts/demo_alert.sh`:**
```bash
#!/bin/bash
ID="demo-$(date +%s)"
curl -s -X POST http://localhost:8001/api/internal/event \
  -H "Content-Type: application/json" \
  -d "{
    \"id\":\"$ID\",
    \"type\":\"WAZUH\",
    \"severity\":\"CRITICAL\",
    \"source\":\"CV-DC05\",
    \"env\":\"CEDERVALL\",
    \"title\":\"Brute force attack detected — 47 failed attempts\",
    \"body\":\"Source IP: 185.220.101.45 | Target: Administrator | EventID: 4625\",
    \"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"speak\":true,
    \"metadata\":{\"rule_level\":14,\"attack_ip\":\"185.220.101.45\"}
  }" > /dev/null
echo "✅ Demo alert injected — check UI and listen for voice."
```

**`scripts/demo_presence.sh`:**
```bash
#!/bin/bash
TS=$(python3 -c "import time; print(int(time.time()))")
curl -s -X POST http://localhost:8001/api/webhook \
  -H "Content-Type: application/json" \
  -d "{
    \"alarm\": {
      \"name\":\"AEGIS Demo\",
      \"sources\":[{\"device\":\"AABBCCDDEEFF\",\"type\":\"include\"}],
      \"triggers\":[{\"key\":\"person\",\"device\":\"AABBCCDDEEFF\"}]
    },
    \"timestamp\":$TS
  }" > /dev/null
echo "✅ Demo presence event sent — check UI and listen for voice."
```

**`scripts/smoke_test.sh`:**
```bash
#!/bin/bash
# NOTERA: set -e ANVÄNDS INTE (skulle bryta FAIL-räknaren)
PASS=0
FAIL=0

check() {
  local desc="$1"
  local cmd="$2"
  local expected="$3"
  local actual
  actual=$(eval "$cmd" 2>/dev/null)
  if echo "$actual" | grep -qE "$expected"; then
    echo "  ✅ $desc"
    PASS=$((PASS+1))
  else
    echo "  ❌ $desc"
    echo "     got:      $actual"
    echo "     expected: $expected"
    FAIL=$((FAIL+1))
  fi
}

echo ""
echo "╔══════════════════════════════════╗"
echo "║     AEGIS SMOKE TEST v4.0        ║"
echo "╚══════════════════════════════════╝"
echo ""

check "orion-hub health" \
  "curl -s http://localhost:8001/health | python3 -c \"import sys,json; print(json.load(sys.stdin)['status'])\"" \
  "operational"

check "openmct-ui HTTP 200" \
  "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080" \
  "200"

check "herald-voice health" \
  "curl -s http://localhost:8002/health | python3 -c \"import sys,json; print(json.load(sys.stdin)['status'])\"" \
  "operational"

check "herald-voice cache populated" \
  "curl -s http://localhost:8002/health | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if d['cache_files']>=9 else d['cache_files'])\"" \
  "ok"

check "WebSocket connection" \
  "python3 -c \"
import asyncio,websockets,json
async def t():
    async with websockets.connect('ws://localhost:8001/ws') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        print(json.loads(msg)['type'])
asyncio.run(t())
\"" \
  "SYSTEM"

check "event ingestion" \
  "curl -s -X POST http://localhost:8001/api/internal/event \
    -H 'Content-Type: application/json' \
    -d '{\"id\":\"smoke-test-$(date +%s)\",\"type\":\"SYSTEM\",\"severity\":\"INFO\",
         \"source\":\"smoke\",\"env\":\"ALL\",\"title\":\"SMOKE TEST\",
         \"body\":\"\",\"timestamp\":\"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'\",
         \"speak\":false,\"metadata\":{}}' \
   | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if d.get('id') else 'fail')\"" \
  "ok"

check "events retrievable" \
  "curl -s 'http://localhost:8001/api/events?limit=5' | python3 -c \"import sys,json; print(len(json.load(sys.stdin)))\"" \
  "[1-9]"

check "AI query responds" \
  "curl -s -X POST http://localhost:8001/api/query \
    -H 'Content-Type: application/json' \
    -d '{\"question\":\"status\",\"env\":\"ALL\"}' \
   | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if len(d.get('answer',''))>5 else 'fail')\"" \
  "ok"

check "status summary has all envs" \
  "curl -s http://localhost:8001/api/status/summary | python3 -c \"
import sys,json; d=json.load(sys.stdin)
expected={'CEDERVALL','VALVX','GWSK','PERSONAL'}
print('ok' if expected.issubset(d.keys()) else 'missing envs')
\"" \
  "ok"

check "webhook accepted" \
  "curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8001/api/webhook \
    -H 'Content-Type: application/json' \
    -d '{\"alarm\":{\"name\":\"t\",\"sources\":[{\"device\":\"AA\",\"type\":\"include\"}],
         \"triggers\":[{\"key\":\"person\",\"device\":\"AA\"}]},\"timestamp\":1}'" \
  "200"

check "demo-alert script executable" \
  "test -x scripts/demo_alert.sh && echo ok" \
  "ok"

check "demo-presence script executable" \
  "test -x scripts/demo_presence.sh && echo ok" \
  "ok"

check "AEGIS_BUILD_LOG.md exists" \
  "test -f AEGIS_BUILD_LOG.md && echo ok" \
  "ok"

echo ""
echo "══════════════════════════════════"
echo "  RESULT: $PASS passed  |  $FAIL failed"
echo "══════════════════════════════════"

if [ $FAIL -eq 0 ]; then
  echo "  ✅ AEGIS READY FOR CUSTOMER DEMO"
  exit 0
else
  echo "  ❌ AEGIS NOT READY — fix failures above"
  exit 1
fi
```

### VERIFY TASK-011

```bash
chmod +x scripts/demo_alert.sh scripts/demo_presence.sh scripts/smoke_test.sh
make smoke
EXPECTED: exit 0, "AEGIS READY FOR CUSTOMER DEMO"
EXPECTED: 13 av 13 checks passerar
```

---

## TASK-012: AEGIS_BUILD_LOG.md och slutstatus

Agenten skriver `AEGIS_BUILD_LOG.md` med exakt detta innehåll:

```markdown
# AEGIS Build Log
Datum: [ISO-datum]
Byggtid: [minuter]
PRD-version: 4.0

## Task Status
| Task | Namn | Status | Försök | Notering |
|------|------|--------|--------|----------|
| 001  | Repo/Procfile/Makefile  | [✅/❌/⚠️] | N | ... |
| 002  | orion-hub               | [✅/❌/⚠️] | N | ... |
| 003  | openmct-ui              | [✅/❌/⚠️] | N | ... |
| 004  | herald-voice            | [✅/❌/⚠️] | N | ... |
| 005  | Wazuh integration       | [✅/❌/⚠️] | N | ... |
| 006  | WinRM integration       | [✅/❌/⚠️] | N | ... |
| 007  | UniFi/Ping/VPN          | [✅/❌/⚠️] | N | ... |
| 008  | sentinel-eye            | [✅/❌/⚠️] | N | ... |
| 009  | AI Query + Context      | [✅/❌/⚠️] | N | ... |
| 010  | Mission Overview        | [✅/❌/⚠️] | N | ... |
| 011  | Demo + Smoke Test       | [✅/❌/⚠️] | N | ... |
| 012  | Build Log               | ✅ OK      | 1 |     |

## Smoke Test Output
[klistra in output från make smoke]

## BLOCKED Tasks
[lista tasks som misslyckades 3 gånger, med felanledning]

## Kända begränsningar
[allt som inte implementerades]

## Operatörsinstruktioner
1. Installera beroenden:
   pip3 install -r requirements.txt

2. Konfigurera nätverk:
   - Kopiera VPN-konfig för ValvX till /etc/openvpn/client/valvx.conf
   - Kopiera VPN-konfig för GWSK  till /etc/openvpn/client/gwsk.conf
   - Starta VPN: sudo openvpn --config /etc/openvpn/client/valvx.conf --daemon

3. Konfigurera credentials:
   cp .env.example .env
   # Fyll i alla värden i .env

4. Konfigurera kameror i .env:
   CAMERA_MAP=MAC1:Serverrum,MAC2:Entré,...

5. Konfigurera UniFi Protect (se README)

6. Starta AEGIS:
   make dev

7. Öppna i Chrome (fullscreen: Cmd+Ctrl+F):
   http://localhost:8080

8. Demo-kommandon:
   make demo-alert      # visar kritiskt larm + röst
   make demo-presence   # visar presence-detektion + röst
   make voice-test      # testar röst
   make smoke           # kör alla tester
```

### VERIFY TASK-012

```bash
test -f AEGIS_BUILD_LOG.md && echo "exists"
EXPECTED: exists

grep -c "Operatörsinstruktioner" AEGIS_BUILD_LOG.md
EXPECTED: 1

python3 -c "
with open('AEGIS_BUILD_LOG.md') as f:
    content = f.read()
tasks = [f'| 0{i:02d}' for i in range(1,13)]
missing = [t for t in tasks if t not in content]
print('ok' if not missing else f'missing tasks: {missing}')
"
EXPECTED: ok
```

---

## Slutacceptans

```
□ pip3 install -r requirements.txt → 0 errors
□ make dev → alla processer startar (honcho + docker)
□ http://localhost:8080 → AEGIS UI fullscreen, ISS-estetik
□ Boot-animation spelas vid sidladdning
□ Röst hörs vid boot: "AEGIS Control online..."
□ Server-grid visar minst 4 hosts med statusfärg
□ ENV-selector har alla fyra miljöer
□ Mission Overview-panel synlig med alla miljöer
□ make demo-alert → röd CRITICAL alert + röst inom 3s
□ make demo-presence → SENSITIVE/INTRUSION overlay + röst
□ AI svarar på fråga inom 8 sekunder
□ make smoke → 13/13 checks gröna, exit 0
□ AEGIS_BUILD_LOG.md komplett
```
