"""
lib/cache.py — two-tier cache: memory + SQLite  (TODO: you implement)
=====================================================================
Why two tiers?
  - MEMORY (dict): instant, but lost on restart.
  - SQLite (disk): survives restarts, and is where you can inspect what your
    service has learned. Check memory first, then disk, then LLM.

The cache key must be deterministic for the same (text, target). Hashing the
input with sha256 gives you a compact, collision-safe key.

Fill in the TODOs. The method signatures and stats are laid out for you.
"""
import hashlib
import time
from typing import Optional

import aiosqlite


def _key(text: str, target: str) -> str:
    return hashlib.sha256(f"{target}::{text}".encode("utf-8")).hexdigest()


class TwoTierCache:
    def __init__(self, db_path: str, ttl_seconds: int = 0):
        """`ttl_seconds` is a bonus/optional feature — 0 (default) means no
        expiry at all, which is the assignment's required behavior. Set it
        via CACHE_TTL_SECONDS in .env to opt into expiring entries.
        """
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self._mem: dict[str, tuple] = {}  # key -> (translated, stored_at_epoch)
        self._stats = {"requests": 0, "memory_hits": 0, "db_hits": 0, "misses": 0}

    def _expired(self, stored_at: float) -> bool:
        return self.ttl_seconds > 0 and (time.time() - stored_at) > self.ttl_seconds

    async def init(self) -> None:
        """Create the translations table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    key TEXT PRIMARY KEY,
                    source TEXT,
                    target TEXT,
                    translated TEXT,
                    model TEXT,
                    access_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_translations_key ON translations(key)")
            await db.commit()

    async def get(self, text: str, target: str) -> Optional[str]:
        """Return a cached translation or None. Check memory, then SQLite."""
        self._stats["requests"] += 1
        k = _key(text, target)

        # 1) memory tier
        if k in self._mem:
            translated, stored_at = self._mem[k]
            if not self._expired(stored_at):
                self._stats["memory_hits"] += 1
                return translated
            del self._mem[k]  # TTL expired — fall through to the SQLite/miss path

        # 2) SQLite tier
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT translated, strftime('%s', created_at) FROM translations WHERE key = ?", (k,)
            ) as cur:
                row = await cur.fetchone()

            if row is not None:
                translated, created_epoch = row
                stored_at = float(created_epoch) if created_epoch is not None else time.time()
                if not self._expired(stored_at):
                    await db.execute(
                        "UPDATE translations SET access_count = access_count + 1 WHERE key = ?",
                        (k,),
                    )
                    await db.commit()
                    self._mem[k] = (translated, stored_at)  # warm the memory tier
                    self._stats["db_hits"] += 1
                    return translated
                # else: expired on disk too — treated as a miss below; `set()`
                # will overwrite this row (and its created_at) on the next write.

        self._stats["misses"] += 1
        return None

    async def set(self, text: str, target: str, translated: str, model: str) -> None:
        """Store a translation in both tiers."""
        k = _key(text, target)
        now = time.time()
        self._mem[k] = (translated, now)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO translations (key, source, target, translated, model)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    translated = excluded.translated,
                    model = excluded.model,
                    access_count = translations.access_count + 1,
                    created_at = CURRENT_TIMESTAMP
                """,
                (k, text, target, translated, model),
            )
            await db.commit()

    async def clear(self) -> dict:
        """Bonus: wipe both cache tiers (e.g. via POST /clear-cache) and reset
        the running request/hit/miss counters. Not required by the assignment
        — the default TTL is 0 (off), so this is purely opt-in behavior.
        """
        mem_cleared = len(self._mem)
        self._mem.clear()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM translations") as cur:
                row = await cur.fetchone()
            db_cleared = row[0] if row else 0
            await db.execute("DELETE FROM translations")
            await db.commit()
        self._stats = {"requests": 0, "memory_hits": 0, "db_hits": 0, "misses": 0}
        return {"memory_entries_cleared": mem_cleared, "db_rows_cleared": db_cleared}

    async def size(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM translations") as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def stats(self) -> dict:
        total = self._stats["memory_hits"] + self._stats["db_hits"] + self._stats["misses"]
        hits = self._stats["memory_hits"] + self._stats["db_hits"]
        hit_rate = round(100 * hits / total, 1) if total else 0.0
        return {**self._stats, "hit_rate_pct": hit_rate, "memory_entries": len(self._mem)}
