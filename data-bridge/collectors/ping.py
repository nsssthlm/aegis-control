"""AEGIS Data Bridge — ICMP ping collector for host availability monitoring."""

import asyncio
import time
from datetime import datetime, timezone

import httpx
from icmplib import ping as icmp_ping

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL = 30  # seconds
PING_COUNT = 3
PING_INTERVAL = 0.5
PING_TIMEOUT = 3
CRITICAL_FAIL_THRESHOLD = 3  # consecutive failures before CRITICAL

ORION_HUB_URL = "http://localhost:8001/api/internal/event"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class PingCollector:
    """Monitors host availability via ICMP ping and reports to Orion Hub."""

    def __init__(self, env: str, targets: dict[str, str]) -> None:
        """
        Args:
            env: Environment name (e.g., "PERSONAL", "CEDERVALL")
            targets: Dict of {hostname: ip_address}
        """
        self.env = env
        self.targets = targets
        self._running = False

        # State tracking per host: {"hostname": {"online": bool, "fail_count": int}}
        self.state: dict[str, dict] = {}
        for hostname in targets:
            self.state[hostname] = {"online": True, "fail_count": 0, "reported_down": False}

    # ------------------------------------------------------------------ #
    # Ping
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _ping_host(ip: str) -> tuple[bool, float]:
        """Ping a host. Returns (is_alive, avg_rtt_ms).

        Uses privileged=False for macOS unprivileged ICMP.
        """
        try:
            result = await asyncio.to_thread(
                icmp_ping,
                ip,
                count=PING_COUNT,
                interval=PING_INTERVAL,
                timeout=PING_TIMEOUT,
                privileged=False,
            )
            return result.is_alive, result.avg_rtt
        except Exception:
            return False, 0.0

    # ------------------------------------------------------------------ #
    # Event helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _make_event(env: str, hostname: str, ip: str, severity: str, title: str,
                    body: str, speak: bool, speak_text: str | None = None) -> dict:
        """Build an Orion Hub event dict."""
        return {
            "id": f"ping-{env.lower()}-{hostname.lower()}-{int(time.time())}",
            "type": "PING",
            "severity": severity,
            "source": hostname,
            "env": env,
            "title": title,
            "body": body,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speak": speak,
            "metadata": {
                "ip": ip,
                "speak_text": speak_text,
            },
        }

    # ------------------------------------------------------------------ #
    # Poll
    # ------------------------------------------------------------------ #

    async def _poll(self, hub_client: httpx.AsyncClient) -> None:
        """Ping all targets and generate events for state changes."""
        for hostname, ip in self.targets.items():
            is_alive, avg_rtt = await self._ping_host(ip)
            state = self.state[hostname]
            was_online = state["online"]

            if is_alive:
                # Host is up
                if not was_online:
                    # Came back online
                    event = self._make_event(
                        self.env, hostname, ip,
                        severity="INFO",
                        title=f"Host {hostname} back online",
                        body=f"RTT: {avg_rtt:.1f}ms | {ip}",
                        speak=False,
                    )
                    try:
                        await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                        print(f"[PING/{self.env}] {hostname} ({ip}) back online (RTT: {avg_rtt:.1f}ms)")
                    except Exception as exc:
                        print(f"[PING/{self.env}] Failed to forward event: {exc}")

                state["online"] = True
                state["fail_count"] = 0
                state["reported_down"] = False

            else:
                # Host is down
                state["fail_count"] += 1
                state["online"] = False

                if was_online and state["fail_count"] == 1:
                    # First failure — WARNING
                    event = self._make_event(
                        self.env, hostname, ip,
                        severity="WARNING",
                        title=f"Host {hostname} unreachable",
                        body=f"First ping failure | {ip}",
                        speak=False,
                    )
                    try:
                        await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                        print(f"[PING/{self.env}] {hostname} ({ip}) unreachable (fail 1)")
                    except Exception as exc:
                        print(f"[PING/{self.env}] Failed to forward event: {exc}")

                elif state["fail_count"] >= CRITICAL_FAIL_THRESHOLD and not state["reported_down"]:
                    # 3+ consecutive failures — CRITICAL with voice
                    speak_text = f"Critical alert. Host {hostname} is unreachable."
                    event = self._make_event(
                        self.env, hostname, ip,
                        severity="CRITICAL",
                        title=f"Host {hostname} is unreachable",
                        body=f"{state['fail_count']} consecutive failures | {ip}",
                        speak=True,
                        speak_text=speak_text,
                    )
                    try:
                        await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                        print(f"[PING/{self.env}] CRITICAL: {hostname} ({ip}) unreachable x{state['fail_count']}")
                    except Exception as exc:
                        print(f"[PING/{self.env}] Failed to forward event: {exc}")

                    state["reported_down"] = True

    # ------------------------------------------------------------------ #
    # Run loop
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Main collector loop."""
        if not self.targets:
            print(f"[PING/{self.env}] No targets configured — skipping")
            return

        self._running = True
        target_list = ", ".join(f"{h}={ip}" for h, ip in self.targets.items())
        print(f"[PING/{self.env}] Starting collector (targets: {target_list})")

        async with httpx.AsyncClient(timeout=5) as hub_client:
            while self._running:
                try:
                    await self._poll(hub_client)
                except Exception as exc:
                    print(f"[PING/{self.env}] Unexpected error: {exc}")

                await asyncio.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the collector to stop."""
        self._running = False
