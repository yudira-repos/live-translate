"""
FDE · Assignment 1 · Python AI Service  (this is the real assignment)
=====================================================================
A small FastAPI service that translates English → Mexican Spanish with:
  - an LLM call            (lib/llm.py)
  - a two-tier cache       (lib/cache.py)  — memory + SQLite
  - structured logging     (lib/logger.py) — provided, wired for you

The Node gateway forwards the browser's requests here. You implement the
TODOs so the widget lights up. Run:

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env          # then add your API key
    uvicorn app:app --reload --port 8000
"""
import os
import time
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from lib.cache import TwoTierCache
from lib.llm import SUPPORTED_TARGETS, translate_text
from lib.logger import get_logger

load_dotenv()

MODEL = os.getenv("MODEL", "claude-sonnet-5")
DB_PATH = os.getenv("TRANSLATION_DB_PATH", "translations.db")
# Bonus/optional: 0 (default) = no expiry, which is the assignment's required
# behavior. Set CACHE_TTL_SECONDS to opt into expiring cache entries.
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "0"))

app = FastAPI(title="FDE Live Translate — AI Service")
log = get_logger("ai-service")
cache = TwoTierCache(DB_PATH, ttl_seconds=CACHE_TTL_SECONDS)

# request/response shapes ----------------------------------------------------
class TranslateIn(BaseModel):
    text: str
    target: str = "es-MX"

class BatchIn(BaseModel):
    texts: list[str]
    target: str = "es-MX"


@app.on_event("startup")
async def startup():
    await cache.init()
    log.info("ai_service_started", extra={"model": MODEL, "db": DB_PATH})


# --- core: translate one string --------------------------------------------
async def translate_one(text: str, target: str) -> dict:
    """Translate a single string, using the cache first.

    Returns a dict shaped exactly like the widget expects:
        {"translated": str, "cached": bool, "latencyMs": int, "model": str}
    """
    text = (text or "").strip()
    if not text:
        return {"translated": "", "cached": False, "latencyMs": 0, "model": MODEL}

    t0 = time.perf_counter()

    cached_value = await cache.get(text, target)
    if cached_value is not None:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {"translated": cached_value, "cached": True, "latencyMs": latency_ms, "model": MODEL}

    # Cache miss: call the LLM, then store the result so the next identical
    # request is a hit. Deliberately NOT wrapped in try/except — a provider
    # error must propagate so the caller can fail loud (502), never silently
    # serve back the untranslated English.
    translated = await translate_text(text, target, model=MODEL)
    await cache.set(text, target, translated, model=MODEL)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {"translated": translated, "cached": False, "latencyMs": latency_ms, "model": MODEL}


@app.post("/translate")
async def translate(body: TranslateIn, x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id")):
    if body.target not in SUPPORTED_TARGETS:
        raise HTTPException(
            status_code=501,
            detail=f"target '{body.target}' is not implemented (supported: {sorted(SUPPORTED_TARGETS)})",
        )
    try:
        result = await translate_one(body.text, body.target)
    except Exception as e:  # noqa: BLE001 — fail loud: log + surface as 502, never fake success
        log.error(
            "translate_failed",
            extra={"error": str(e), "chars": len(body.text), "requestId": x_request_id},
        )
        raise HTTPException(status_code=502, detail=f"LLM translation failed: {e}") from e

    log.info(
        "translate",
        extra={
            "cached": result["cached"],
            "latencyMs": result["latencyMs"],
            "chars": len(body.text),
            "requestId": x_request_id,
        },
    )
    return result


@app.post("/translate/batch")
async def translate_batch(body: BatchIn, x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id")):
    if body.target not in SUPPORTED_TARGETS:
        raise HTTPException(
            status_code=501,
            detail=f"target '{body.target}' is not implemented (supported: {sorted(SUPPORTED_TARGETS)})",
        )
    t0 = time.perf_counter()
    try:
        results = [await translate_one(t, body.target) for t in body.texts]
    except Exception as e:  # noqa: BLE001 — same fail-loud policy as /translate
        log.error(
            "translate_batch_failed",
            extra={"error": str(e), "count": len(body.texts), "requestId": x_request_id},
        )
        raise HTTPException(status_code=502, detail=f"LLM translation failed: {e}") from e

    latency = int((time.perf_counter() - t0) * 1000)
    hits = sum(1 for r in results if r["cached"])
    log.info(
        "translate_batch",
        extra={"count": len(results), "hits": hits, "latencyMs": latency, "requestId": x_request_id},
    )
    # widget expects {results: [{translated, cached}], latencyMs}
    return {"results": [{"translated": r["translated"], "cached": r["cached"]} for r in results], "latencyMs": latency}


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL, "cacheSize": await cache.size()}


@app.get("/stats")
async def stats():
    return await cache.stats()


@app.post("/clear-cache")
async def clear_cache(x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id")):
    """Bonus/optional endpoint: wipe both cache tiers and reset stats."""
    result = await cache.clear()
    log.info("cache_cleared", extra={**result, "requestId": x_request_id})
    return {"status": "ok", **result}
