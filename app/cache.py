import logging
import os
import time

from app.config import CACHE_TTL_HOURS
from app.db import clear_cached_path, get_stale_tracks

logger = logging.getLogger("cache_cleanup")


async def cleanup_stale_cache() -> None:
    cutoff = time.time() - CACHE_TTL_HOURS * 3600
    stale = await get_stale_tracks(cutoff)

    for youtube_id, cached_path in stale:
        if cached_path and os.path.exists(cached_path):
            try:
                os.remove(cached_path)
            except OSError as e:
                logger.warning("Не удалось удалить %s: %s", cached_path, e)
        await clear_cached_path(youtube_id)

    if stale:
        logger.info("Очищено из кэша: %d треков", len(stale))
