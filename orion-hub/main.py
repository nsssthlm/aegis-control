"""AEGIS Orion Hub — Central FastAPI communication hub.

Runs on port 8001. Provides:
- WebSocket event broadcast
- REST API for events, status, AI queries
- UniFi webhook receiver
- SQLite persistence with WAL mode
"""

import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# Ensure the orion-hub directory is on the import path so that
# `import config`, `from services import ...`, `from routers import ...`
# all work regardless of how uvicorn is launched.
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

import config
from services import database, event_bus
from routers import websocket, query, webhook, status

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Application start time ───────────────────────────────────────────
_start_time: float = 0.0


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown sequence."""
    global _start_time

    print("=" * 60)
    print("  AEGIS ORION HUB — Startup Sequence")
    print("=" * 60)

    # 1. Validate configuration
    print("[STARTUP] Validating configuration...")
    config.validate()
    print("[STARTUP] Configuration OK")

    # 2. Initialize SQLite with WAL mode
    print("[STARTUP] Initializing database...")
    await database.init()

    # 3. Start event bus
    print("[STARTUP] Starting event bus...")
    await event_bus.start()

    # 4. Record start time
    _start_time = time.time()
    status.set_start_time(_start_time)

    # 5. Broadcast SYSTEM event: AEGIS online
    boot_event = {
        "id": str(uuid.uuid4()),
        "type": "SYSTEM",
        "severity": "INFO",
        "source": "orion-hub",
        "env": "ALL",
        "title": "AEGIS online",
        "body": "Orion Hub started. All subsystems nominal.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "speak": True,
        "metadata": {"version": "4.0"},
    }
    await database.insert_event(boot_event)
    await event_bus.publish(boot_event)

    # Send to herald-voice for spoken announcement
    await status._send_to_herald(boot_event["title"], boot_event["severity"])

    print("[STARTUP] AEGIS online — broadcasting system event")
    print(f"[STARTUP] Listening on port {config.AEGIS_ORION_PORT}")
    print("=" * 60)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    print("[SHUTDOWN] Stopping event bus...")
    await event_bus.stop()
    print("[SHUTDOWN] Closing database...")
    await database.close()
    print("[SHUTDOWN] AEGIS Orion Hub offline.")


# ── FastAPI app ──────────────────────────────────────────────────────

app = FastAPI(
    title="AEGIS Orion Hub",
    description="Central communication hub for AEGIS mission control",
    version="4.0",
    lifespan=lifespan,
)

# CORS — allow the Open MCT UI and any local dev tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ────────────────────────────────────────────────
app.include_router(websocket.router)
app.include_router(query.router)
app.include_router(webhook.router)
app.include_router(status.router)


# ── Root endpoint ────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint — confirms the hub is running."""
    return {
        "service": "AEGIS Orion Hub",
        "version": "4.0",
        "status": "operational",
    }
