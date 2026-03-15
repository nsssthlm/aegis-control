"""AEGIS status and event endpoints."""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from services import database, event_bus

router = APIRouter()

# Track uptime from module load (overridden on startup)
_start_time: float = time.time()


def set_start_time(t: float) -> None:
    """Set the application start time for uptime calculation."""
    global _start_time
    _start_time = t


# ── Pydantic models ──────────────────────────────────────────────────

class EventIn(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = Field(
        ...,
        pattern=r"^(SYSTEM|WAZUH|WINRM|UNIFI|PRESENCE|INTRUSION|SENSITIVE|PING|VPN|AI)$",
    )
    severity: str = Field(
        ...,
        pattern=r"^(INFO|WARNING|CRITICAL|INTRUSION|SENSITIVE)$",
    )
    source: str = Field(..., max_length=120)
    env: str = Field(
        ...,
        pattern=r"^(CEDERVALL|VALVX|GWSK|PERSONAL|ALL)$",
    )
    title: str = Field(..., max_length=80)
    body: str = Field("", max_length=500)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    speak: bool = False
    metadata: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: int
    connected_clients: int


class EnvStatus(BaseModel):
    status: str
    alerts_24h: int
    threat_level: str
    last_event: Optional[str]
    servers: List[str]


class StatusSummary(BaseModel):
    CEDERVALL: EnvStatus
    VALVX: EnvStatus
    GWSK: EnvStatus
    PERSONAL: EnvStatus


# ── Server mapping per environment ───────────────────────────────────

ENV_SERVERS = {
    "CEDERVALL": ["CV-DC05", "CV-APP01", "CV-FS01", "CV-WAZUH01"],
    "VALVX": ["VX-DC01", "VX-APP01", "VX-WAZUH01"],
    "GWSK": ["GW-FW01", "GW-DC01"],
    "PERSONAL": ["CryptoEdge", "MBG6", "Neurogenisys"],
}

HERALD_VOICE_URL = "http://localhost:8002/speak"


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="operational",
        version="4.0",
        uptime_seconds=int(time.time() - _start_time),
        connected_clients=event_bus.client_count(),
    )


@router.post("/api/internal/event")
async def receive_event(event: EventIn):
    """Receive an event, persist it, broadcast via WebSocket.

    If speak=True, also POST to herald-voice.
    """
    event_dict = event.model_dump()

    # Persist to SQLite
    await database.insert_event(event_dict)

    # Broadcast to all WebSocket clients
    await event_bus.publish(event_dict)

    # If speak is requested, send to herald-voice
    if event.speak:
        await _send_to_herald(event.title, event.severity)

    return {"status": "accepted", "id": event.id}


@router.get("/api/events")
async def list_events(
    env: Optional[str] = Query(None, pattern=r"^(CEDERVALL|VALVX|GWSK|PERSONAL|ALL)$"),
    severity: Optional[str] = Query(None, pattern=r"^(INFO|WARNING|CRITICAL|INTRUSION|SENSITIVE)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Query events, newest first. Optional env/severity filters."""
    # If env is ALL, don't filter by env
    actual_env = None if env == "ALL" else env
    events = await database.get_events(
        env=actual_env, severity=severity, limit=limit, offset=offset
    )
    return events


@router.get("/api/status/summary", response_model=StatusSummary)
async def status_summary():
    """Aggregated status per environment."""
    result = {}

    for env_name, servers in ENV_SERVERS.items():
        counts = await database.get_events_count_by_env_and_severity(env_name, hours=24)
        total_alerts = sum(counts.values())
        critical = counts.get("CRITICAL", 0)
        intrusion = counts.get("INTRUSION", 0)

        # Determine threat level
        if intrusion > 0:
            threat = "CRITICAL"
        elif critical > 0:
            threat = "HIGH"
        elif total_alerts > 5:
            threat = "MEDIUM"
        else:
            threat = "LOW"

        # Determine overall status
        if intrusion > 0 or critical > 2:
            status = "alert"
        elif critical > 0 or total_alerts > 10:
            status = "degraded"
        else:
            status = "nominal"

        last = await database.get_last_event_for_env(env_name)
        last_event_title = last["title"] if last else None

        result[env_name] = EnvStatus(
            status=status,
            alerts_24h=total_alerts,
            threat_level=threat,
            last_event=last_event_title,
            servers=servers,
        )

    return StatusSummary(**result)


# ── Herald voice integration ────────────────────────────────────────

async def _send_to_herald(title: str, severity: str) -> None:
    """Send a speak request to herald-voice. Fire-and-forget."""
    priority = 10 if severity in ("CRITICAL", "INTRUSION") else 5
    payload = {"text": title, "priority": priority}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(HERALD_VOICE_URL, json=payload)
            if resp.status_code != 200:
                print(f"[STATUS] herald-voice returned {resp.status_code}")
    except httpx.ConnectError:
        print("[STATUS] herald-voice not reachable — voice disabled")
    except Exception as exc:
        print(f"[STATUS] Herald error: {exc}")
