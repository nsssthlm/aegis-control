"""AEGIS Data Bridge — UniFi Network API collector."""

import asyncio
import time
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL = 30  # seconds
API_TIMEOUT = 5
ORION_HUB_URL = "http://localhost:8001/api/internal/event"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class UniFiCollector:
    """Polls UniFi Network API for client/device metrics and WAN status."""

    def __init__(self, env: str, config: dict) -> None:
        self.env = env
        self.url = config.get("unifi_url", "").rstrip("/")
        self.api_key = config.get("unifi_key", "")
        self._running = False
        self.fail_count = 0
        self._site_id = None  # discovered at first poll

        # WAN state tracking
        self._wan_was_up: bool | None = None

        if not self.url or not self.api_key:
            print(f"[UNIFI/{self.env}] WARNING: Incomplete config — collector will not start")

    # ------------------------------------------------------------------ #
    # API helpers
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        """Build request headers with API key auth."""
        return {
            "X-API-KEY": self.api_key,
            "Accept": "application/json",
        }

    async def _discover_site_id(self, client: httpx.AsyncClient) -> str:
        """Discover the first site ID from the UniFi API."""
        url = f"{self.url}/proxy/network/integration/v1/sites"
        resp = await client.get(url, headers=self._headers(), timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        sites = data.get("data", [])
        if sites:
            site_id = sites[0].get("id", "default")
            print(f"[UNIFI/{self.env}] Discovered site: {sites[0].get('name', '?')} ({site_id})")
            return site_id
        return "default"

    async def _get_site_id(self, client: httpx.AsyncClient) -> str:
        """Get site ID, discovering it on first call."""
        if self._site_id is None:
            self._site_id = await self._discover_site_id(client)
        return self._site_id

    async def _fetch_clients(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch connected clients from UniFi API."""
        site = await self._get_site_id(client)
        url = f"{self.url}/proxy/network/integration/v1/sites/{site}/clients"
        resp = await client.get(url, headers=self._headers(), timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", data) if isinstance(data, dict) else data

    async def _fetch_devices(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch network devices from UniFi API."""
        site = await self._get_site_id(client)
        url = f"{self.url}/proxy/network/integration/v1/sites/{site}/devices"
        resp = await client.get(url, headers=self._headers(), timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", data) if isinstance(data, dict) else data

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #

    def _analyze_devices(self, devices: list[dict]) -> tuple[bool, dict]:
        """Analyze device data. Returns (wan_is_up, metrics_dict)."""
        wan_up = True
        total_devices = len(devices)
        adopted = 0
        offline_devices = []

        for dev in devices:
            state = dev.get("state", "")
            name = dev.get("name", dev.get("mac", "unknown"))

            if state == "CONNECTED" or state == "ONLINE":
                adopted += 1
            elif state == "OFFLINE" or state == "DISCONNECTED":
                offline_devices.append(name)

            # Check for WAN port status on gateways/routers
            if dev.get("type") in ("ugw", "udm", "uxg") or "gateway" in name.lower():
                wan_status = dev.get("wan1", {}).get("status", "")
                if wan_status and wan_status not in ("connected", "CONNECTED", "up", "UP"):
                    wan_up = False
                # Also check uplink
                uplink = dev.get("uplink", {})
                if uplink and uplink.get("up") is False:
                    wan_up = False

        metrics = {
            "total_devices": total_devices,
            "adopted": adopted,
            "offline": offline_devices,
        }
        return wan_up, metrics

    def _analyze_clients(self, clients: list[dict]) -> dict:
        """Analyze client data. Returns metrics dict."""
        total = len(clients)
        wired = sum(1 for c in clients if not c.get("is_wired", True) is False and c.get("type") == "WIRED")
        wireless = total - wired

        return {
            "total_clients": total,
            "wired": wired,
            "wireless": wireless,
        }

    # ------------------------------------------------------------------ #
    # Poll
    # ------------------------------------------------------------------ #

    async def _poll(self, api_client: httpx.AsyncClient, hub_client: httpx.AsyncClient) -> None:
        """Execute one poll cycle."""
        # Fetch data
        clients = await self._fetch_clients(api_client)
        devices = await self._fetch_devices(api_client)

        # Analyze
        wan_up, device_metrics = self._analyze_devices(devices)
        client_metrics = self._analyze_clients(clients)

        # Merge metrics
        metrics = {**device_metrics, **client_metrics}

        # Send INFO metrics event
        metrics_event = {
            "id": f"unifi-{self.env.lower()}-metrics-{int(time.time())}",
            "type": "UNIFI",
            "severity": "INFO",
            "source": "unifi-controller",
            "env": self.env,
            "title": f"UniFi: {metrics['total_clients']} clients, {metrics['total_devices']} devices",
            "body": (
                f"Clients: {metrics['total_clients']} (wired: {metrics['wired']}, wireless: {metrics['wireless']}) | "
                f"Devices: {metrics['total_devices']} (adopted: {metrics['adopted']})"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speak": False,
            "metadata": metrics,
        }

        try:
            await hub_client.post(ORION_HUB_URL, json=metrics_event, timeout=5)
        except Exception as exc:
            print(f"[UNIFI/{self.env}] Failed to forward metrics: {exc}")

        # Report offline devices
        if device_metrics["offline"]:
            for dev_name in device_metrics["offline"]:
                offline_event = {
                    "id": f"unifi-{self.env.lower()}-offline-{dev_name.lower().replace(' ', '-')}-{int(time.time())}",
                    "type": "UNIFI",
                    "severity": "WARNING",
                    "source": dev_name,
                    "env": self.env,
                    "title": f"UniFi device {dev_name} offline",
                    "body": f"Device {dev_name} is reporting OFFLINE status",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "speak": False,
                    "metadata": {"device_name": dev_name},
                }
                try:
                    await hub_client.post(ORION_HUB_URL, json=offline_event, timeout=5)
                except Exception as exc:
                    print(f"[UNIFI/{self.env}] Failed to forward offline event: {exc}")

        # WAN status change detection
        if self._wan_was_up is not None:
            if self._wan_was_up and not wan_up:
                # WAN went down — CRITICAL immediately
                speak_text = "Critical alert. WAN connectivity lost."
                wan_event = {
                    "id": f"unifi-{self.env.lower()}-wan-down-{int(time.time())}",
                    "type": "UNIFI",
                    "severity": "CRITICAL",
                    "source": "unifi-controller",
                    "env": self.env,
                    "title": "WAN connectivity lost",
                    "body": "UniFi gateway reports WAN link is down",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "speak": True,
                    "metadata": {"speak_text": speak_text, "wan_up": False},
                }
                try:
                    await hub_client.post(ORION_HUB_URL, json=wan_event, timeout=5)
                    print(f"[UNIFI/{self.env}] CRITICAL: WAN connectivity lost")
                except Exception as exc:
                    print(f"[UNIFI/{self.env}] Failed to forward WAN event: {exc}")

            elif not self._wan_was_up and wan_up:
                # WAN came back
                wan_event = {
                    "id": f"unifi-{self.env.lower()}-wan-up-{int(time.time())}",
                    "type": "UNIFI",
                    "severity": "INFO",
                    "source": "unifi-controller",
                    "env": self.env,
                    "title": "WAN connectivity restored",
                    "body": "UniFi gateway reports WAN link is back online",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "speak": False,
                    "metadata": {"wan_up": True},
                }
                try:
                    await hub_client.post(ORION_HUB_URL, json=wan_event, timeout=5)
                    print(f"[UNIFI/{self.env}] INFO: WAN connectivity restored")
                except Exception as exc:
                    print(f"[UNIFI/{self.env}] Failed to forward WAN event: {exc}")

        self._wan_was_up = wan_up

    # ------------------------------------------------------------------ #
    # Run loop
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Main collector loop."""
        if not self.url or not self.api_key:
            print(f"[UNIFI/{self.env}] Skipping — incomplete configuration")
            return

        self._running = True
        print(f"[UNIFI/{self.env}] Starting collector (url={self.url})")

        async with httpx.AsyncClient(verify=False, timeout=API_TIMEOUT) as api_client, \
                   httpx.AsyncClient(timeout=5) as hub_client:

            while self._running:
                try:
                    await self._poll(api_client, hub_client)
                    self.fail_count = 0
                except Exception as exc:
                    self.fail_count += 1
                    print(f"[UNIFI/{self.env}] Error (fail {self.fail_count}): {exc}")

                    if self.fail_count >= 5:
                        print(f"[UNIFI/{self.env}] Too many failures — waiting 60s")
                        self.fail_count = 0
                        await asyncio.sleep(60)
                        continue

                    await asyncio.sleep(30)
                    continue

                await asyncio.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the collector to stop."""
        self._running = False
