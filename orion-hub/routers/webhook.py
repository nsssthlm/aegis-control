"""AEGIS UniFi webhook receiver — POST /api/webhook."""

from fastapi import APIRouter, BackgroundTasks, Request, Response

import httpx

router = APIRouter()

SENTINEL_EYE_URL = "http://localhost:8003/process"


async def _forward_to_sentinel(payload: dict) -> None:
    """Forward the raw UniFi payload to sentinel-eye for processing.

    Fire-and-forget. Errors are logged but never propagate.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(SENTINEL_EYE_URL, json=payload)
            if resp.status_code != 200:
                print(
                    f"[WEBHOOK] sentinel-eye returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
    except httpx.ConnectError:
        print("[WEBHOOK] sentinel-eye not reachable at " + SENTINEL_EYE_URL)
    except Exception as exc:
        print(f"[WEBHOOK] Forward error: {exc}")


@router.post("/api/webhook")
async def unifi_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive raw UniFi Protect payload.

    Returns 200 immediately (< 100ms). Forwards payload to
    sentinel-eye in the background.
    """
    payload = await request.json()
    background_tasks.add_task(_forward_to_sentinel, payload)
    return Response(status_code=200, content="OK")
