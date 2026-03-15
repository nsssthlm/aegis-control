"""AEGIS Data Bridge — Wazuh Indexer (OpenSearch) collector."""

import asyncio
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL = 15  # seconds
MAX_SEEN_IDS = 1000
PRUNE_COUNT = 100

ORION_HUB_URL = "http://localhost:8001/api/internal/event"

SEARCH_BODY = {
    "query": {
        "range": {
            "rule.level": {"gte": 7}
        }
    },
    "sort": [{"@timestamp": {"order": "desc"}}],
    "size": 50,
    "_source": [
        "rule.level",
        "rule.description",
        "agent.name",
        "agent.ip",
        "@timestamp",
        "rule.groups",
    ],
}


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class WazuhCollector:
    """Polls Wazuh Indexer for high-severity alerts and forwards to Orion Hub."""

    def __init__(self, env: str, config: dict) -> None:
        self.env = env
        self.url = config.get("wazuh_url", "")
        self.user = config.get("wazuh_user", "")
        self.password = config.get("wazuh_password", "")
        self.seen_ids: OrderedDict[str, None] = OrderedDict()
        self.fail_count = 0
        self._running = False

        if not self.url or not self.user:
            print(f"[WAZUH/{self.env}] WARNING: Incomplete config — collector will not start")

    # ------------------------------------------------------------------ #
    # Severity mapping
    # ------------------------------------------------------------------ #

    @staticmethod
    def _map_severity(level: int) -> tuple[str, bool, str | None]:
        """Map Wazuh rule level to (severity, speak, speak_text_prefix).

        Returns:
            (severity, should_speak, speak_text_or_None)
        """
        if level >= 12:
            return "CRITICAL", True, "Critical alert"
        elif level >= 10:
            return "CRITICAL", True, "Advisory"
        else:
            # 7-9
            return "WARNING", False, None

    # ------------------------------------------------------------------ #
    # Dedup
    # ------------------------------------------------------------------ #

    def _is_seen(self, doc_id: str) -> bool:
        """Check if a document ID has been seen before."""
        if doc_id in self.seen_ids:
            return True
        self.seen_ids[doc_id] = None
        if len(self.seen_ids) > MAX_SEEN_IDS:
            # Remove oldest PRUNE_COUNT entries
            for _ in range(PRUNE_COUNT):
                self.seen_ids.popitem(last=False)
        return False

    # ------------------------------------------------------------------ #
    # Build event
    # ------------------------------------------------------------------ #

    def _build_event(self, hit: dict) -> dict | None:
        """Transform a Wazuh hit into an Orion Hub event dict. Returns None if seen."""
        doc_id = hit.get("_id", "")
        if self._is_seen(doc_id):
            return None

        source = hit.get("_source", {})
        level = int(source.get("rule", {}).get("level", 0))
        desc = source.get("rule", {}).get("description", "Unknown alert")
        agent_name = source.get("agent", {}).get("name", "unknown")
        agent_ip = source.get("agent", {}).get("ip", "")
        timestamp = source.get("@timestamp", datetime.now(timezone.utc).isoformat())
        groups = source.get("rule", {}).get("groups", [])

        severity, should_speak, speak_prefix = self._map_severity(level)

        # Build speak text
        speak_text = None
        if should_speak:
            if speak_prefix == "Critical alert":
                speak_text = f"Critical alert. {desc[:60]}. Immediate attention required."
            else:
                speak_text = f"Advisory. {desc[:60]}"

        event = {
            "id": f"wazuh-{self.env.lower()}-{doc_id}",
            "type": "WAZUH",
            "severity": severity,
            "source": agent_name,
            "env": self.env,
            "title": desc,
            "body": f"Agent: {agent_name} ({agent_ip}) | Level: {level} | Groups: {', '.join(groups) if groups else 'N/A'}",
            "timestamp": timestamp,
            "speak": should_speak,
            "metadata": {
                "rule_level": level,
                "agent_ip": agent_ip,
                "groups": groups,
                "speak_text": speak_text,
            },
        }
        return event

    # ------------------------------------------------------------------ #
    # Poll
    # ------------------------------------------------------------------ #

    async def _poll(self, client: httpx.AsyncClient, hub_client: httpx.AsyncClient) -> int:
        """Execute one poll cycle. Returns number of new events forwarded."""
        search_url = f"{self.url.rstrip('/')}/wazuh-alerts-4.x-*/_search"

        resp = await client.post(
            search_url,
            json=SEARCH_BODY,
            auth=httpx.BasicAuth(self.user, self.password),
        )
        resp.raise_for_status()

        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        forwarded = 0

        for hit in hits:
            event = self._build_event(hit)
            if event is None:
                continue

            try:
                await hub_client.post(ORION_HUB_URL, json=event, timeout=5)
                forwarded += 1
            except Exception as exc:
                print(f"[WAZUH/{self.env}] Failed to forward event: {exc}")

        return forwarded

    # ------------------------------------------------------------------ #
    # Run loop
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Main collector loop with circuit breaker."""
        if not self.url or not self.user:
            print(f"[WAZUH/{self.env}] Skipping — incomplete configuration")
            return

        self._running = True
        print(f"[WAZUH/{self.env}] Starting collector (url={self.url})")

        async with httpx.AsyncClient(verify=False, timeout=10) as client, \
                   httpx.AsyncClient(timeout=5) as hub_client:

            while self._running:
                try:
                    count = await self._poll(client, hub_client)
                    if count > 0:
                        print(f"[WAZUH/{self.env}] Forwarded {count} new event(s)")
                    self.fail_count = 0

                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status == 401:
                        print(f"[WAZUH/{self.env}] Wazuh auth failed (401) — waiting 60s")
                        await asyncio.sleep(60)
                        continue
                    self.fail_count += 1
                    print(f"[WAZUH/{self.env}] HTTP {status} (fail {self.fail_count})")

                except Exception as exc:
                    self.fail_count += 1
                    print(f"[WAZUH/{self.env}] Error (fail {self.fail_count}): {exc}")

                # Circuit breaker
                if self.fail_count >= 5:
                    print(f"[WAZUH/{self.env}] Circuit breaker tripped — sending VPN event, waiting 60s")
                    try:
                        vpn_event = {
                            "id": f"wazuh-circuit-{self.env.lower()}-{int(time.time())}",
                            "type": "VPN",
                            "severity": "WARNING",
                            "source": "data-bridge",
                            "env": self.env,
                            "title": f"Wazuh collector circuit breaker tripped — {self.env} unreachable",
                            "body": f"Wazuh at {self.url} failed {self.fail_count} consecutive times",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "speak": False,
                            "metadata": {"fail_count": self.fail_count},
                        }
                        await hub_client.post(ORION_HUB_URL, json=vpn_event, timeout=5)
                    except Exception:
                        pass
                    self.fail_count = 0
                    await asyncio.sleep(60)
                    continue

                if self.fail_count > 0:
                    await asyncio.sleep(30)
                else:
                    await asyncio.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the collector to stop."""
        self._running = False
