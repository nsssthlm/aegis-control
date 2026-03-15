# AEGIS Build Log
Datum: 2026-03-15
PRD-version: 4.0

## Task Status
| Task | Namn | Status | Notering |
|------|------|--------|----------|
| 001  | Repo/Procfile/Makefile  | ✅ OK | Scaffold complete |
| 002  | orion-hub               | ✅ OK | FastAPI + WebSocket + SQLite + AI |
| 003  | openmct-ui              | ✅ OK | NASA ISS dashboard (12 files) |
| 004  | herald-voice            | ✅ OK | TTS with OpenAI nova + afplay |
| 005  | Wazuh integration       | ✅ OK | Wazuh poller with circuit breaker |
| 006  | WinRM integration       | ✅ OK | Windows Event Log via CredSSP |
| 007  | UniFi/Ping/VPN          | ✅ OK | Network monitoring (3 collectors) |
| 008  | sentinel-eye            | ✅ OK | Presence detection + work hours |
| 009  | AI Query + Context      | ✅ OK | gpt-4.1 with context injection |
| 010  | Mission Overview        | ✅ OK | 6-panel NASA layout |
| 011  | Demo + Smoke Test       | ✅ OK | Scripts written |
| 012  | Build Log               | ✅ OK | This file |

## Smoke Test Output
[Will be populated after `make smoke`]

## Kanda begransningar
- herald-voice kraver macOS `afplay` for ljud (Linux: byt till `aplay` eller `mpv`)
- Wazuh/WinRM collectors ansluter ej utan VPN (startar supervised, auto-retry var 10s)
- icmplib kors med `privileged=False` (macOS-kompatibel, men ICMP kan blockeras av brandvagg)
- herald-voice pre-cache kraver OPENAI_API_KEY vid startup

## Operatorsinstruktioner
1. Installera beroenden:
   pip3 install -r requirements.txt

2. Konfigurera natverk:
   - Kopiera VPN-konfig for ValvX till /etc/openvpn/client/valvx.conf
   - Kopiera VPN-konfig for GWSK  till /etc/openvpn/client/gwsk.conf
   - Starta VPN: sudo openvpn --config /etc/openvpn/client/valvx.conf --daemon

3. Konfigurera credentials:
   cp .env.example .env
   # Fyll i alla varden i .env

4. Konfigurera kameror i .env:
   CAMERA_MAP=MAC1:Serverrum,MAC2:Entre,...

5. Konfigurera UniFi Protect (se README)

6. Starta AEGIS:
   make dev

7. Oppna i Chrome (fullscreen: Cmd+Ctrl+F):
   http://localhost:8080

8. Demo-kommandon:
   make demo-alert      # visar kritiskt larm + rost
   make demo-presence   # visar presence-detektion + rost
   make voice-test      # testar rost
   make smoke           # kor alla tester
