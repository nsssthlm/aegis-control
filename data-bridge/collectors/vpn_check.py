"""AEGIS Data Bridge — VPN tunnel status checker."""

import asyncio
import subprocess
import time
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL = 60  # seconds
ORION_HUB_URL = "http://localhost:8001/api/internal/event"

# Tunnel definitions: (interface, env_label)
TUNNELS = [
    ("tun0", "ValvX"),
    ("tun1", "GWSK"),
]


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class VPNCheckCollector:
    """Monitors VPN tunnel interfaces and reports state changes to Orion Hub."""

    def __init__(self) -> None:
        self._running = False

        # State tracking per interface:
        # None = never checked, True = up, False = down
        self.state: dict[str, bool | None] = {}
        for iface, _ in TUNNELS:
            self.state[iface] = None

        # Track whether we've logged "not configured" to avoid spam
        self._not_configured_logged: set[str] = set()

    # ------------------------------------------------------------------ #
    # Check interface
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _check_interface(iface: str) -> bool:
        """Check if a tunnel interface is up and has an IP address."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["ifconfig", iface],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and "inet " in result.stdout
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Poll
    # ------------------------------------------------------------------ #

    async def _poll(self, hub_client: httpx.AsyncClient) -> None:
        """Check all tunnel interfaces and generate events for state changes."""
        for iface, label in TUNNELS:
            is_up = await self._check_interface(iface)
            was_up = self.state[iface]

            if was_up is None:
                # First check
                if is_up:
                    self.state[iface] = True
                    print(f"[VPN] {iface} ({label}) is UP")
                else:
                    self.state[iface] = False
                    if iface not in self._not_configured_logged:
                        print(f"[VPN] {iface} ({label}) not configured — ignoring")
                        self._not_configured_logged.add(iface)
                continue

            if was_up and not is_up:
                # Tunnel went down
                self.state[iface] = False
                speak_text = f"VPN {iface} ({label}) disconnected"
                event = {
                    "id": f"vpn-{iface}-down-{int(time.time())}",
                    "type": "VPN",
                    "severity": "WARNING",
                    "source": iface,
                    "env": label.upper(),
                    "title": f"VPN {iface} ({label}) disconnected",
                    "body": f"Tunnel interface {iface} is no longer active",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "speak": True,
                    "metadata": {
                        "interface": iface,
                        "label": label,
                        "speak_text": speak_text,
                    },
                }
                try:
                    await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                    print(f"[VPN] WARNING: {iface} ({label}) disconnected")
                except Exception as exc:
                    print(f"[VPN] Failed to forward event: {exc}")

            elif not was_up and is_up:
                # Tunnel came back up
                self.state[iface] = True
                event = {
                    "id": f"vpn-{iface}-up-{int(time.time())}",
                    "type": "VPN",
                    "severity": "INFO",
                    "source": iface,
                    "env": label.upper(),
                    "title": f"VPN {iface} ({label}) connected",
                    "body": f"Tunnel interface {iface} is now active",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "speak": False,
                    "metadata": {
                        "interface": iface,
                        "label": label,
                    },
                }
                try:
                    await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                    print(f"[VPN] INFO: {iface} ({label}) connected")
                except Exception as exc:
                    print(f"[VPN] Failed to forward event: {exc}")

    # ------------------------------------------------------------------ #
    # Run loop
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Main collector loop."""
        self._running = True
        print("[VPN] Starting VPN tunnel monitor")

        async with httpx.AsyncClient(timeout=5) as hub_client:
            while self._running:
                try:
                    await self._poll(hub_client)
                except Exception as exc:
                    print(f"[VPN] Unexpected error: {exc}")

                await asyncio.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the collector to stop."""
        self._running = False
