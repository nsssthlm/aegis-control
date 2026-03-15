"""AEGIS Data Bridge — Windows Event Log collector via WinRM/CredSSP."""

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL = 30  # seconds
WINRM_TIMEOUT = 10  # seconds per call
ORION_HUB_URL = "http://localhost:8001/api/internal/event"

# Brute force detection thresholds
BRUTE_FORCE_THRESHOLD = 5
BRUTE_FORCE_WINDOW = 60  # seconds

# PowerShell query — fetches last 35 seconds of security/system events
PS_QUERY = r"""
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

# Event ID → (severity, title, speak)
EVENT_MAP = {
    4625: ("WARNING", "Failed logon attempt", False),
    4648: ("WARNING", "Explicit credential use", False),
    7045: ("CRITICAL", "New service installed", True),
    1102: ("CRITICAL", "AUDIT LOG CLEARED", True),
    4740: ("WARNING", "Account locked out", False),
    4776: ("INFO", "NTLM authentication attempt", False),
}


# ---------------------------------------------------------------------------
# WinRM helper (uses pywinrm)
# ---------------------------------------------------------------------------


def _run_winrm_command(host: str, user: str, password: str, domain: str, script: str) -> str:
    """Execute a PowerShell script via WinRM/CredSSP. Returns stdout as string.

    This is a blocking call — must be run in a thread.
    """
    import winrm

    endpoint = f"https://{host}:5986/wsman"
    session = winrm.Session(
        endpoint,
        auth=(f"{domain}\\{user}", password),
        transport="credssp",
        server_cert_validation="ignore",
        read_timeout_sec=WINRM_TIMEOUT,
        operation_timeout_sec=WINRM_TIMEOUT,
    )
    result = session.run_ps(script)

    if result.status_code != 0:
        stderr = result.std_err.decode("utf-8", errors="replace").strip()
        if stderr:
            raise RuntimeError(f"PowerShell error (exit {result.status_code}): {stderr[:200]}")

    return result.std_out.decode("utf-8", errors="replace").strip()


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class WinRMCollector:
    """Polls Windows Event Logs via WinRM and forwards events to Orion Hub."""

    def __init__(self, env: str, config: dict) -> None:
        self.env = env
        self.host = config.get("winrm_host", "")
        self.user = config.get("winrm_user", "")
        self.password = config.get("winrm_password", "")
        self.domain = config.get("winrm_domain", "")
        self.fail_count = 0
        self._running = False

        # Brute force tracking: {source_ip: [timestamps]}
        self.failed_logons: dict[str, list[float]] = defaultdict(list)

        if not self.host or not self.user:
            print(f"[WINRM/{self.env}] WARNING: Incomplete config — collector will not start")

    # ------------------------------------------------------------------ #
    # Brute force detection
    # ------------------------------------------------------------------ #

    def _check_brute_force(self, source_ip: str, now: float) -> bool:
        """Track failed logons and detect brute force.

        Returns True if brute force detected (and clears the tracking for that IP).
        """
        if not source_ip or source_ip == "-":
            return False

        # Clean old timestamps
        self.failed_logons[source_ip] = [
            ts for ts in self.failed_logons[source_ip]
            if now - ts < BRUTE_FORCE_WINDOW
        ]

        self.failed_logons[source_ip].append(now)

        if len(self.failed_logons[source_ip]) >= BRUTE_FORCE_THRESHOLD:
            # Brute force detected — clear and return True
            del self.failed_logons[source_ip]
            return True

        return False

    # ------------------------------------------------------------------ #
    # Parse and build events
    # ------------------------------------------------------------------ #

    def _parse_events(self, raw: str) -> list[dict]:
        """Parse PowerShell JSON output into list of event dicts for Orion Hub."""
        if not raw or raw == "[]":
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[WINRM/{self.env}] JSON parse error: {exc}")
            return []

        # PowerShell may return a single object instead of array
        if isinstance(data, dict):
            data = [data]

        events = []
        now = time.time()

        for item in data:
            event_id = item.get("Id", 0)
            if event_id not in EVENT_MAP:
                continue

            severity, title, should_speak = EVENT_MAP[event_id]
            message = item.get("Message", "")[:300]
            subject_user = item.get("SubjectUser", "")
            time_created = item.get("TimeCreated", datetime.now(timezone.utc).isoformat())

            # Normalize timestamp — PowerShell may return /Date(...)/ format
            if isinstance(time_created, str) and "/Date(" in time_created:
                try:
                    ms = int(time_created.split("(")[1].split(")")[0].rstrip("/"))
                    time_created = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
                except (ValueError, IndexError):
                    time_created = datetime.now(timezone.utc).isoformat()

            # Speak text for critical events
            speak_text = None
            if should_speak:
                speak_text = f"Critical alert. {title} on {self.host}. Immediate attention required."

            event = {
                "id": f"winrm-{self.env.lower()}-{event_id}-{int(now * 1000)}-{len(events)}",
                "type": "WINRM",
                "severity": severity,
                "source": self.host,
                "env": self.env,
                "title": f"{title} (EventID {event_id})",
                "body": f"User: {subject_user} | {message[:200]}",
                "timestamp": time_created if isinstance(time_created, str) else datetime.now(timezone.utc).isoformat(),
                "speak": should_speak,
                "metadata": {
                    "event_id": event_id,
                    "subject_user": subject_user,
                    "speak_text": speak_text,
                },
            }
            events.append(event)

            # Brute force detection for failed logons
            if event_id == 4625:
                # Try to extract source IP from message
                source_ip = self._extract_source_ip(message)
                if self._check_brute_force(source_ip, now):
                    bf_event = {
                        "id": f"winrm-bf-{self.env.lower()}-{source_ip}-{int(now)}",
                        "type": "WINRM",
                        "severity": "CRITICAL",
                        "source": self.host,
                        "env": self.env,
                        "title": f"Brute force attack from {source_ip}",
                        "body": f"{BRUTE_FORCE_THRESHOLD}+ failed logon attempts from {source_ip} within {BRUTE_FORCE_WINDOW}s",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "speak": True,
                        "metadata": {
                            "event_id": 4625,
                            "attack_ip": source_ip,
                            "speak_text": f"Critical alert. Brute force attack detected from {source_ip}.",
                        },
                    }
                    events.append(bf_event)

        return events

    @staticmethod
    def _extract_source_ip(message: str) -> str:
        """Try to extract source IP from Windows event message."""
        # Common patterns in logon failure events
        for marker in ("Source Network Address:", "Källnätverksadress:"):
            if marker in message:
                after = message.split(marker, 1)[1].strip()
                ip = after.split()[0].strip()
                if ip and ip != "-":
                    return ip
        return ""

    # ------------------------------------------------------------------ #
    # Poll
    # ------------------------------------------------------------------ #

    async def _poll(self, hub_client: httpx.AsyncClient) -> int:
        """Execute one poll cycle. Returns number of events forwarded."""
        # Run WinRM in a thread to avoid blocking the event loop
        raw = await asyncio.to_thread(
            _run_winrm_command,
            self.host,
            self.user,
            self.password,
            self.domain,
            PS_QUERY,
        )

        events = self._parse_events(raw)
        forwarded = 0

        for event in events:
            try:
                await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                forwarded += 1
            except Exception as exc:
                print(f"[WINRM/{self.env}] Failed to forward event: {exc}")

        return forwarded

    # ------------------------------------------------------------------ #
    # Run loop
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Main collector loop with error handling."""
        if not self.host or not self.user:
            print(f"[WINRM/{self.env}] Skipping — incomplete configuration")
            return

        self._running = True
        print(f"[WINRM/{self.env}] Starting collector (host={self.host}, domain={self.domain})")

        async with httpx.AsyncClient(timeout=5) as hub_client:
            while self._running:
                try:
                    count = await self._poll(hub_client)
                    if count > 0:
                        print(f"[WINRM/{self.env}] Forwarded {count} event(s)")
                    self.fail_count = 0

                except Exception as exc:
                    self.fail_count += 1
                    print(f"[WINRM/{self.env}] Error (fail {self.fail_count}): {exc}")

                    if self.fail_count >= 5:
                        print(f"[WINRM/{self.env}] Too many failures — waiting 60s")
                        self.fail_count = 0
                        await asyncio.sleep(60)
                        continue

                    await asyncio.sleep(30)
                    continue

                await asyncio.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the collector to stop."""
        self._running = False
