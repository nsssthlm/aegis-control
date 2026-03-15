"""AEGIS Data Bridge — PowerShell API Gateway collector for Cedervall.

Instead of direct WinRM, Cedervall uses a PowerShell API Gateway on CV-NSS001.
All AD and server monitoring goes through HTTPS POST to :8443/api/execute.

Flow: AEGIS → HTTPS → CV-NSS001 → WinRM (internal) → Target servers
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

POLL_INTERVAL = 30  # seconds
ORION_HUB_URL = "http://localhost:8001/api/internal/event"

# PowerShell scripts for monitoring
HEALTH_SCRIPT = r"""
$results = @()
$computers = @('CV-DC05','CV-DC06','CV-FS01','CV-FS02','CV-FS05','CV-APP1','CV-APP03','CV-APP05')
foreach ($c in $computers) {
    try {
        $r = Invoke-Command -ComputerName $c -ScriptBlock {
            $cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
            $mem = Get-CimInstance Win32_OperatingSystem
            $memPct = [math]::Round(($mem.TotalVisibleMemorySize - $mem.FreePhysicalMemory) / $mem.TotalVisibleMemorySize * 100, 1)
            $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" |
                Select-Object @{N='UsedPct';E={[math]::Round(($_.Size - $_.FreeSpace) / $_.Size * 100, 1)}}
            @{cpu=$cpu; mem=$memPct; disk=$disk.UsedPct; hostname=$env:COMPUTERNAME}
        } -ErrorAction Stop
        $results += @{name=$c; status='online'; cpu=$r.cpu; mem=$r.mem; disk=$r.disk}
    } catch {
        $results += @{name=$c; status='offline'; error=$_.Exception.Message}
    }
}
$results | ConvertTo-Json -Depth 3
"""

SECURITY_SCRIPT = r"""
$cutoff = (Get-Date).AddSeconds(-35)
$events = Get-WinEvent -FilterHashtable @{
    LogName='Security';
    Id=@(4625,4648,7045,1102,4740,4776);
    StartTime=$cutoff
} -ErrorAction SilentlyContinue | Select-Object Id, TimeCreated, Message -First 50
$events | ForEach-Object {
    @{
        id = $_.Id
        time = $_.TimeCreated.ToString('o')
        msg = $_.Message.Substring(0, [Math]::Min($_.Message.Length, 200))
    }
} | ConvertTo-Json -Depth 2
"""

# Security event ID mapping
EVENT_MAP = {
    4625: ("WARNING", "Failed logon attempt", False),
    4648: ("INFO", "Explicit credential logon", False),
    7045: ("WARNING", "New service installed", True),
    1102: ("CRITICAL", "Audit log cleared", True),
    4740: ("WARNING", "Account locked out", True),
    4776: ("INFO", "Credential validation", False),
}


class PowerShellAPICollector:
    """Monitors Cedervall infrastructure via the CV-NSS001 PowerShell API Gateway."""

    def __init__(self, config: dict) -> None:
        self.env = "CEDERVALL"
        self.jump_url = config.get("jump_url", "").rstrip("/")
        self.api_key = config.get("jump_api_key", "")
        self._running = False
        self._brute_force_tracker: dict[str, list[float]] = {}  # ip -> [timestamps]

        if not self.jump_url or not self.api_key:
            print("[PS-API/CEDERVALL] WARNING: Incomplete config")

    async def _execute(
        self, client: httpx.AsyncClient, script: str, computer: str = "localhost"
    ) -> Optional[dict | list]:
        """Execute a PowerShell script via the API gateway."""
        try:
            resp = await client.post(
                f"{self.jump_url}/api/execute",
                json={"computer": computer, "script": script},
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # The API returns the PowerShell output; parse if needed
            if isinstance(data, (dict, list)):
                return data
            # Sometimes it returns a wrapper with 'output' key
            if isinstance(data, dict) and "output" in data:
                output = data["output"]
                if isinstance(output, str):
                    return json.loads(output)
                return output
            return data
        except httpx.HTTPStatusError as exc:
            print(f"[PS-API/CEDERVALL] HTTP {exc.response.status_code}: {exc.response.text[:200]}")
            return None
        except json.JSONDecodeError:
            # Raw text response — try to parse
            try:
                return json.loads(resp.text)
            except Exception:
                print(f"[PS-API/CEDERVALL] Non-JSON response: {resp.text[:200]}")
                return None
        except Exception as exc:
            print(f"[PS-API/CEDERVALL] Error: {exc}")
            return None

    async def _check_health(
        self, api_client: httpx.AsyncClient, hub_client: httpx.AsyncClient
    ) -> None:
        """Run health checks on all Cedervall servers."""
        result = await self._execute(api_client, HEALTH_SCRIPT)
        if result is None:
            return

        servers = result if isinstance(result, list) else [result]

        for srv in servers:
            name = srv.get("name", "unknown")
            status = srv.get("status", "unknown")

            if status == "offline":
                event = {
                    "id": f"psapi-health-{name.lower()}-{int(time.time())}",
                    "type": "PING",
                    "severity": "CRITICAL",
                    "source": name,
                    "env": self.env,
                    "title": f"Server {name} unreachable",
                    "body": srv.get("error", "No response from WinRM"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "speak": True,
                    "metadata": {"server": name, "status": "offline"},
                }
                try:
                    await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                except Exception:
                    pass
            else:
                cpu = srv.get("cpu", 0)
                mem = srv.get("mem", 0)
                disk = srv.get("disk", 0)

                # Alert on high resource usage
                severity = "INFO"
                speak = False
                alerts = []

                if cpu and cpu > 90:
                    severity = "WARNING"
                    alerts.append(f"CPU {cpu}%")
                if mem and mem > 95:
                    severity = "CRITICAL"
                    speak = True
                    alerts.append(f"RAM {mem}%")
                if disk and disk > 90:
                    severity = "WARNING"
                    alerts.append(f"Disk {disk}%")
                    if disk > 95:
                        severity = "CRITICAL"
                        speak = True

                if alerts:
                    event = {
                        "id": f"psapi-resource-{name.lower()}-{int(time.time())}",
                        "type": "SYSTEM",
                        "severity": severity,
                        "source": name,
                        "env": self.env,
                        "title": f"{name}: {', '.join(alerts)}",
                        "body": f"CPU: {cpu}% | RAM: {mem}% | Disk: {disk}%",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "speak": speak,
                        "metadata": {"cpu": cpu, "mem": mem, "disk": disk},
                    }
                    try:
                        await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                    except Exception:
                        pass

    async def _check_security(
        self, api_client: httpx.AsyncClient, hub_client: httpx.AsyncClient
    ) -> None:
        """Check Windows Security events on DC."""
        result = await self._execute(api_client, SECURITY_SCRIPT, computer="CV-DC05")
        if result is None:
            return

        events = result if isinstance(result, list) else [result]
        now = time.time()

        for evt in events:
            event_id = evt.get("id", 0)
            if event_id not in EVENT_MAP:
                continue

            severity, title_prefix, should_speak = EVENT_MAP[event_id]
            msg = evt.get("msg", "")

            # Brute force detection for 4625
            if event_id == 4625:
                # Extract source IP from message if possible
                source_ip = "unknown"
                if "Source Network Address:" in msg:
                    try:
                        source_ip = msg.split("Source Network Address:")[1].strip().split()[0]
                    except (IndexError, ValueError):
                        pass

                if source_ip != "unknown":
                    if source_ip not in self._brute_force_tracker:
                        self._brute_force_tracker[source_ip] = []
                    self._brute_force_tracker[source_ip].append(now)
                    # Clean old entries (60s window)
                    self._brute_force_tracker[source_ip] = [
                        t for t in self._brute_force_tracker[source_ip] if now - t < 60
                    ]
                    count = len(self._brute_force_tracker[source_ip])
                    if count >= 5:
                        bf_event = {
                            "id": f"psapi-bruteforce-{int(now)}",
                            "type": "WAZUH",
                            "severity": "CRITICAL",
                            "source": "CV-DC05",
                            "env": self.env,
                            "title": f"Brute force attack from {source_ip} — {count} attempts",
                            "body": msg[:200],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "speak": True,
                            "metadata": {"source_ip": source_ip, "attempts": count, "event_id": 4625},
                        }
                        try:
                            await hub_client.post(ORION_HUB_URL, json=bf_event, timeout=5)
                        except Exception:
                            pass
                        self._brute_force_tracker[source_ip] = []
                        continue

            event = {
                "id": f"psapi-sec-{event_id}-{int(now)}-{uuid.uuid4().hex[:6]}",
                "type": "WINRM",
                "severity": severity,
                "source": "CV-DC05",
                "env": self.env,
                "title": f"{title_prefix} (EventID {event_id})",
                "body": msg[:300],
                "timestamp": evt.get("time", datetime.now(timezone.utc).isoformat()),
                "speak": should_speak,
                "metadata": {"event_id": event_id},
            }
            try:
                await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
            except Exception:
                pass

    async def run(self) -> None:
        """Main collector loop."""
        if not self.jump_url or not self.api_key:
            print("[PS-API/CEDERVALL] Skipping — incomplete configuration")
            return

        self._running = True
        print(f"[PS-API/CEDERVALL] Starting collector (gateway={self.jump_url})")

        async with httpx.AsyncClient(verify=False, timeout=30) as api_client, \
                   httpx.AsyncClient(timeout=5) as hub_client:

            # Initial health check of jump server
            try:
                resp = await api_client.get(
                    f"{self.jump_url}/api/health",
                    headers={"X-API-Key": self.api_key},
                )
                print(f"[PS-API/CEDERVALL] Jump server health: {resp.text[:100]}")
            except Exception as exc:
                print(f"[PS-API/CEDERVALL] Jump server unreachable: {exc}")

            cycle = 0
            while self._running:
                try:
                    # Health check every cycle (30s)
                    await self._check_health(api_client, hub_client)

                    # Security check every cycle
                    await self._check_security(api_client, hub_client)

                    cycle += 1
                    if cycle % 10 == 0:
                        print(f"[PS-API/CEDERVALL] Cycle {cycle} complete")

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    print(f"[PS-API/CEDERVALL] Error in cycle {cycle}: {exc}")

                await asyncio.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the collector to stop."""
        self._running = False
