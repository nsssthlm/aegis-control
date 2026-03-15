"""AEGIS event bus — asyncio queue with WebSocket broadcast."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, List, Optional, Set

from fastapi import WebSocket

# Active WebSocket clients
_clients: Set[WebSocket] = set()

# Incoming event queue
_queue: asyncio.Queue = asyncio.Queue()

# Background task handle
_broadcast_task: Optional[asyncio.Task] = None


def get_clients() -> Set[WebSocket]:
    """Return the set of active WebSocket clients."""
    return _clients


def client_count() -> int:
    """Return the number of connected clients."""
    return len(_clients)


async def register(ws: WebSocket) -> None:
    """Register a new WebSocket client."""
    _clients.add(ws)
    print(f"[EVENT_BUS] Client connected ({client_count()} total)")


async def unregister(ws: WebSocket) -> None:
    """Remove a WebSocket client. Never crashes."""
    _clients.discard(ws)
    print(f"[EVENT_BUS] Client disconnected ({client_count()} total)")


async def publish(event: dict) -> None:
    """Put an event on the queue for broadcast."""
    await _queue.put(event)


async def _broadcast_loop() -> None:
    """Consume events from the queue and broadcast to all connected clients.

    Events are broadcast within 500ms of being published. Disconnected
    clients are silently removed.
    """
    while True:
        try:
            event = await asyncio.wait_for(_queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break

        if not _clients:
            continue

        payload = json.dumps(event)
        stale: List[WebSocket] = []

        for ws in _clients.copy():
            try:
                await asyncio.wait_for(ws.send_text(payload), timeout=0.5)
            except Exception:
                stale.append(ws)

        # Remove disconnected clients
        for ws in stale:
            _clients.discard(ws)
        if stale:
            print(f"[EVENT_BUS] Removed {len(stale)} stale client(s)")


async def start() -> None:
    """Start the broadcast loop as a background task."""
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.create_task(_broadcast_loop())
        print("[EVENT_BUS] Broadcast loop started")


async def stop() -> None:
    """Stop the broadcast loop and close all clients."""
    global _broadcast_task
    if _broadcast_task and not _broadcast_task.done():
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
    _broadcast_task = None

    # Close all connected clients
    for ws in _clients.copy():
        try:
            await ws.close()
        except Exception:
            pass
    _clients.clear()
    print("[EVENT_BUS] Stopped")
