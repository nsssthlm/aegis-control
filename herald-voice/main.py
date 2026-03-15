"""AEGIS Herald Voice — TTS service with queue, caching, and pre-cached boot phrases."""

import asyncio
import hashlib
import os
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = Path("/tmp/aegis-voice")
CACHE_TTL_SECONDS = 86400  # 24 hours
TTS_MODEL = "tts-1"
TTS_VOICE = "nova"
TTS_SPEED = 0.92

BOOT_PHRASES = [
    "AEGIS Control online. All systems nominal. Awaiting operator input.",
    "Switching to CEDERVALL environment. Loading telemetry.",
    "Switching to VALVX environment. Loading telemetry.",
    "Switching to GWSK environment. Loading telemetry.",
    "Switching to PERSONAL environment. Loading telemetry.",
    "Attention. Personnel detected. Sensitive information protocols active.",
    "Warning. Unauthorized access detected. Security breach in progress.",
    "Critical alert. Immediate attention required.",
    "AEGIS Control going offline. Goodbye.",
]

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="AEGIS Herald Voice", version="1.0.0")

# The playback queue: items are (text, filepath) tuples
_queue: asyncio.Queue[tuple[str, Path]] = asyncio.Queue(maxsize=3)
_worker_task: asyncio.Task | None = None
_client: AsyncOpenAI | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cache_key(text: str) -> str:
    """SHA-256 of text + voice + speed for deterministic cache naming."""
    raw = f"{text}{TTS_VOICE}{TTS_SPEED}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(text: str) -> Path:
    """Return the filesystem path for a cached TTS file."""
    return CACHE_DIR / f"{_cache_key(text)}.mp3"


def _clean_old_cache() -> int:
    """Remove cache files older than TTL. Returns count of removed files."""
    if not CACHE_DIR.exists():
        return 0
    now = time.time()
    removed = 0
    for f in CACHE_DIR.iterdir():
        if f.suffix == ".mp3" and (now - f.stat().st_mtime) > CACHE_TTL_SECONDS:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _cache_file_count() -> int:
    """Count .mp3 files in the cache directory."""
    if not CACHE_DIR.exists():
        return 0
    return sum(1 for f in CACHE_DIR.iterdir() if f.suffix == ".mp3")


async def _synthesize(text: str) -> Path:
    """Call OpenAI TTS API and cache the result. Returns path to MP3."""
    filepath = _cache_path(text)
    if filepath.exists():
        return filepath

    if _client is None:
        raise RuntimeError("OpenAI client not initialized")

    response = await _client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        speed=TTS_SPEED,
        response_format="mp3",
    )

    # Write to a temp file first, then rename for atomicity
    tmp_path = filepath.with_suffix(".tmp")
    try:
        tmp_path.write_bytes(response.content)
        tmp_path.rename(filepath)
    except Exception:
        # Clean up temp file on failure
        tmp_path.unlink(missing_ok=True)
        raise

    return filepath


async def _precache_boot_phrases() -> None:
    """Pre-cache all boot phrases at startup. Errors are logged, not fatal."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("[HERALD] No OPENAI_API_KEY — skipping pre-cache")
        return

    cached = 0
    skipped = 0
    for phrase in BOOT_PHRASES:
        filepath = _cache_path(phrase)
        if filepath.exists():
            skipped += 1
            continue
        try:
            await _synthesize(phrase)
            cached += 1
        except Exception as exc:
            print(f"[HERALD] Pre-cache failed for '{phrase[:40]}...': {exc}")

    print(f"[HERALD] Pre-cache complete: {cached} new, {skipped} already cached")


# ---------------------------------------------------------------------------
# Playback worker
# ---------------------------------------------------------------------------


async def _playback_worker() -> None:
    """Background worker: dequeue audio files and play them with afplay."""
    while True:
        try:
            text, filepath = await _queue.get()
        except asyncio.CancelledError:
            break

        try:
            print(f"[HERALD] Playing: {text[:60]}...")
            # Run afplay in a thread so we don't block the event loop
            await asyncio.to_thread(
                subprocess.run,
                ["afplay", "-v", "0.9", str(filepath)],
                check=False,
                capture_output=True,
            )
        except Exception as exc:
            print(f"[HERALD] Playback error: {exc}")
        finally:
            _queue.task_done()

        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SpeakRequest(BaseModel):
    text: str
    priority: int = 5


class SpeakResponse(BaseModel):
    queued: bool
    cached: bool


class HealthResponse(BaseModel):
    status: str
    queue_size: int
    cache_files: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/speak", response_model=SpeakResponse)
async def speak(req: SpeakRequest) -> SpeakResponse:
    """Queue text for TTS playback. Returns immediately."""
    # Check cache before synthesis
    was_cached = _cache_path(req.text).exists()

    # Synthesize (returns cached path if already exists)
    try:
        filepath = await _synthesize(req.text)
    except Exception as exc:
        print(f"[HERALD] TTS synthesis error: {exc}")
        return SpeakResponse(queued=False, cached=False)

    # If queue is full, drop the oldest item to make room
    if _queue.full():
        try:
            _queue.get_nowait()
            _queue.task_done()
            print("[HERALD] Queue full — dropped oldest item")
        except asyncio.QueueEmpty:
            pass

    try:
        _queue.put_nowait((req.text, filepath))
    except asyncio.QueueFull:
        print("[HERALD] Queue still full after drop — this should not happen")
        return SpeakResponse(queued=False, cached=was_cached)

    return SpeakResponse(queued=True, cached=was_cached)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="operational",
        queue_size=_queue.qsize(),
        cache_files=_cache_file_count(),
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup() -> None:
    global _worker_task, _client

    # Ensure cache directory exists
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Clean old cache files
    removed = _clean_old_cache()
    if removed:
        print(f"[HERALD] Cleaned {removed} expired cache files")

    # Initialize OpenAI client
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        _client = AsyncOpenAI(api_key=api_key)
        print("[HERALD] OpenAI client initialized")
    else:
        print("[HERALD] WARNING: No OPENAI_API_KEY set — TTS will fail")

    # Start playback worker
    _worker_task = asyncio.create_task(_playback_worker())
    print("[HERALD] Playback worker started")

    # Pre-cache boot phrases in background (non-blocking)
    asyncio.create_task(_precache_boot_phrases())

    print("[HERALD] Herald Voice service online on port 8002")


@app.on_event("shutdown")
async def shutdown() -> None:
    global _worker_task, _client

    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None

    if _client:
        await _client.close()
        _client = None

    print("[HERALD] Herald Voice service offline")
