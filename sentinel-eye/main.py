"""AEGIS Sentinel Eye — UniFi Protect webhook processor with presence logic."""

import os
import sys
import time
from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STOCKHOLM = ZoneInfo("Europe/Stockholm")
ORION_HUB_URL = "http://localhost:8001/api/internal/event"
THROTTLE_SECONDS = 60  # per camera

# Parse CAMERA_MAP from env: "MAC1:Name1,MAC2:Name2"
_raw_camera_map = os.getenv("CAMERA_MAP", "")
CAMERA_MAP: Dict[str, str] = {}
if _raw_camera_map:
    for pair in _raw_camera_map.split(","):
        pair = pair.strip()
        if ":" in pair:
            mac, name = pair.split(":", 1)
            CAMERA_MAP[mac.strip().upper()] = name.strip()

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="AEGIS Sentinel Eye", version="1.0.0")

# Throttle state: {camera_mac: last_event_timestamp}
_last_event: Dict[str, float] = {}

# HTTP client for forwarding to Orion Hub
_hub_client: Optional[httpx.AsyncClient] = None


# ---------------------------------------------------------------------------
# Presence logic
# ---------------------------------------------------------------------------


def _is_work_hours(dt: datetime) -> bool:
    """Check if datetime falls within work hours (Mon-Fri 8:00-18:00 Stockholm time)."""
    local = dt.astimezone(STOCKHOLM)
    # weekday(): 0=Monday, 6=Sunday
    if local.weekday() >= 5:
        return False
    return 8 <= local.hour < 18


def _get_camera_name(mac: str) -> str:
    """Resolve camera MAC to human name. Falls back to MAC address."""
    return CAMERA_MAP.get(mac.upper(), mac)


def _is_throttled(mac: str) -> bool:
    """Check if we should throttle events for this camera."""
    now = time.time()
    last = _last_event.get(mac)
    if last is not None and (now - last) < THROTTLE_SECONDS:
        return True
    _last_event[mac] = now
    return False


# ---------------------------------------------------------------------------
# Webhook parsing
# ---------------------------------------------------------------------------


def _parse_protect_payload(payload: dict) -> Optional[dict]:
    """Parse a UniFi Protect webhook payload.

    Returns a dict with keys: camera_mac, camera_name, trigger_key, timestamp
    or None if the payload is not relevant.
    """
    alarm = payload.get("alarm", {})
    triggers = alarm.get("triggers", [])
    if not triggers:
        return None

    # Find a "person" trigger
    person_trigger = None
    for trigger in triggers:
        if trigger.get("key") == "person":
            person_trigger = trigger
            break

    if person_trigger is None:
        return None

    # Get camera MAC from trigger or from alarm sources
    camera_mac = person_trigger.get("device", "")
    if not camera_mac:
        sources = alarm.get("sources", [])
        for source in sources:
            if source.get("type") == "include":
                camera_mac = source.get("device", "")
                break

    if not camera_mac:
        return None

    camera_mac = camera_mac.upper()
    camera_name = _get_camera_name(camera_mac)

    # Timestamp from payload (Unix seconds) or now
    ts = payload.get("timestamp")
    if ts:
        try:
            timestamp = datetime.fromtimestamp(int(ts), tz=STOCKHOLM)
        except (ValueError, TypeError, OSError):
            timestamp = datetime.now(tz=STOCKHOLM)
    else:
        timestamp = datetime.now(tz=STOCKHOLM)

    return {
        "camera_mac": camera_mac,
        "camera_name": camera_name,
        "trigger_key": "person",
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/process")
async def process_webhook(request: Request) -> dict:
    """Receive UniFi Protect webhook payload, run presence logic, forward to Orion Hub."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "reason": "invalid json"}

    parsed = _parse_protect_payload(payload)
    if parsed is None:
        return {"status": "ignored", "reason": "no person trigger"}

    camera_mac = parsed["camera_mac"]
    camera_name = parsed["camera_name"]
    timestamp = parsed["timestamp"]

    # Throttle: 60s per camera
    if _is_throttled(camera_mac):
        return {"status": "throttled", "camera": camera_name}

    # Determine event type based on work hours
    work_hours = _is_work_hours(timestamp)

    if work_hours:
        severity = "SENSITIVE"
        title = f"Personnel detected — {camera_name}"
        speak_text = "Attention. Personnel detected. Sensitive information protocols active."
        event_type = "PRESENCE"
    else:
        severity = "INTRUSION"
        title = f"After-hours intrusion — {camera_name}"
        speak_text = "Warning. Unauthorized access detected. Security breach in progress."
        event_type = "INTRUSION"

    event = {
        "id": f"sentinel-{camera_mac.lower()}-{int(time.time())}",
        "type": event_type,
        "severity": severity,
        "source": camera_name,
        "env": "CEDERVALL",
        "title": title,
        "body": f"Camera: {camera_name} (MAC: {camera_mac}) | Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "timestamp": timestamp.astimezone(ZoneInfo("UTC")).isoformat(),
        "speak": True,
        "metadata": {
            "camera_mac": camera_mac,
            "camera_name": camera_name,
            "work_hours": work_hours,
            "speak_text": speak_text,
            "local_time": timestamp.strftime("%H:%M:%S"),
        },
    }

    # Forward to Orion Hub
    if _hub_client:
        try:
            await _hub_client.post(ORION_HUB_URL, json=event, timeout=5)
            print(f"[SENTINEL] {severity}: {title}")
        except Exception as exc:
            print(f"[SENTINEL] Failed to forward event: {exc}")
    else:
        print(f"[SENTINEL] WARNING: Hub client not initialized — event not forwarded")

    return {"status": "processed", "event_type": event_type, "camera": camera_name}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "operational",
        "cameras_configured": len(CAMERA_MAP),
        "active_throttles": sum(
            1 for mac, ts in _last_event.items()
            if time.time() - ts < THROTTLE_SECONDS
        ),
    }


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup() -> None:
    global _hub_client
    _hub_client = httpx.AsyncClient(timeout=5)

    print("[SENTINEL] ========================================")
    print("[SENTINEL] AEGIS Sentinel Eye online on port 8003")
    print(f"[SENTINEL] Cameras configured: {len(CAMERA_MAP)}")
    for mac, name in CAMERA_MAP.items():
        print(f"[SENTINEL]   {mac} → {name}")
    print(f"[SENTINEL] Throttle: {THROTTLE_SECONDS}s per camera")
    print(f"[SENTINEL] Timezone: {STOCKHOLM}")
    print("[SENTINEL] ========================================")


@app.on_event("shutdown")
async def shutdown() -> None:
    global _hub_client
    if _hub_client:
        await _hub_client.aclose()
        _hub_client = None
    print("[SENTINEL] Sentinel Eye offline")


# ---------------------------------------------------------------------------
# Entry point for `python3 -m main`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8003, reload=False)
