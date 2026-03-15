"""AEGIS WebSocket endpoint — client broadcast with heartbeat."""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services import event_bus

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # seconds
MAX_MISSED_PONGS = 3


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket connection handler.

    - Broadcasts all events to connected clients.
    - Sends PING every 30s, expects PONG.
    - Closes connection after 3 missed PONGs.
    """
    await ws.accept()
    await event_bus.register(ws)

    missed_pongs = 0
    expecting_pong = False

    async def _heartbeat():
        """Send periodic PING messages."""
        nonlocal missed_pongs, expecting_pong
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if expecting_pong:
                missed_pongs += 1
                if missed_pongs >= MAX_MISSED_PONGS:
                    print(f"[WEBSOCKET] Client missed {MAX_MISSED_PONGS} pongs — closing")
                    await ws.close(code=1000, reason="Heartbeat timeout")
                    return
            try:
                await ws.send_text(json.dumps({"type": "PING"}))
                expecting_pong = True
            except Exception:
                return

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if msg.get("type") == "PONG":
                expecting_pong = False
                missed_pongs = 0
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[WEBSOCKET] Connection error: {exc}")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await event_bus.unregister(ws)
