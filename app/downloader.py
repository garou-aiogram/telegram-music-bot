import asyncio
import os

import yt_dlp

from app.config import CACHE_DIR
from app.db import get_cached_path, set_cached_path, touch_last_accessed

_locks: dict[str, asyncio.Lock] = {}


def _get_lock(youtube_id: str) -> asyncio.Lock:
    if youtube_id not in _locks:
        _locks[youtube_id] = asyncio.Lock()
    return _locks[youtube_id]


def _download_sync(youtube_id: str) -> str:
    output_template = str(CACHE_DIR / f"{youtube_id}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # YouTube иногда отдаёт 403 Forbidden на прямые ссылки для "веб"-клиента.
        # Android-клиент реже блокируется — стандартный обход в yt-dlp.
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
    }

    url = f"https://www.youtube.com/watch?v={youtube_id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    final_path = CACHE_DIR / f"{youtube_id}.mp3"
    if not final_path.exists():
        raise RuntimeError(f"yt-dlp/ffmpeg не создали файл для {youtube_id}")
    return str(final_path)


async def get_or_download(youtube_id: str) -> str:
    """Возвращает путь к mp3. Использует кэш из БД, если файл ещё существует на диске."""
    cached_path = await get_cached_path(youtube_id)
    if cached_path and os.path.exists(cached_path):
        await touch_last_accessed(youtube_id)
        return cached_path

    lock = _get_lock(youtube_id)
    async with lock:
        # повторная проверка — вдруг файл появился, пока ждали лок
        cached_path = await get_cached_path(youtube_id)
        if cached_path and os.path.exists(cached_path):
            return cached_path

        path = await asyncio.to_thread(_download_sync, youtube_id)
        await set_cached_path(youtube_id, path)
        return path
