import time

import aiosqlite

from app.config import DB_PATH

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    first_seen REAL
)
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tracks (
    youtube_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT,
    duration_seconds INTEGER,
    thumbnail_url TEXT,
    cached_path TEXT,
    telegram_file_id TEXT,
    last_accessed REAL
)
"""


async def _ensure_column(db: aiosqlite.Connection, column: str, ddl_type: str) -> None:
    """Добавляет колонку, если её ещё нет (для баз, созданных до этого изменения)."""
    cursor = await db.execute("PRAGMA table_info(tracks)")
    existing_columns = {row[1] for row in await cursor.fetchall()}
    if column not in existing_columns:
        await db.execute(f"ALTER TABLE tracks ADD COLUMN {column} {ddl_type}")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TABLE_SQL)
        await db.execute(CREATE_USERS_TABLE_SQL)
        await _ensure_column(db, "telegram_file_id", "TEXT")
        await db.commit()


async def add_user(chat_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (chat_id, username, first_seen) VALUES (?, ?, ?)",
            (chat_id, username, time.time()),
        )
        await db.commit()


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT chat_id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def get_track_metadata(youtube_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT youtube_id, title, artist, duration_seconds, thumbnail_url FROM tracks WHERE youtube_id = ?",
            (youtube_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def upsert_track_metadata(track: dict) -> None:
    """Сохраняет/обновляет метаданные трека (без пути к файлу — это отдельно)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO tracks (youtube_id, title, artist, duration_seconds, thumbnail_url)
            VALUES (:youtube_id, :title, :artist, :duration_seconds, :thumbnail_url)
            ON CONFLICT(youtube_id) DO UPDATE SET
                title=excluded.title,
                artist=excluded.artist,
                duration_seconds=excluded.duration_seconds,
                thumbnail_url=excluded.thumbnail_url
            """,
            track,
        )
        await db.commit()


async def get_telegram_file_id(youtube_id: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT telegram_file_id FROM tracks WHERE youtube_id = ?", (youtube_id,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_telegram_file_id(youtube_id: str, file_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracks SET telegram_file_id = ?, last_accessed = ? WHERE youtube_id = ?",
            (file_id, time.time(), youtube_id),
        )
        await db.commit()


async def get_cached_path(youtube_id: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT cached_path FROM tracks WHERE youtube_id = ?", (youtube_id,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_cached_path(youtube_id: str, path: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracks SET cached_path = ?, last_accessed = ? WHERE youtube_id = ?",
            (path, time.time(), youtube_id),
        )
        await db.commit()


async def touch_last_accessed(youtube_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tracks SET last_accessed = ? WHERE youtube_id = ?", (time.time(), youtube_id))
        await db.commit()


async def get_stale_tracks(cutoff_timestamp: float) -> list[tuple[str, str]]:
    """Возвращает (youtube_id, cached_path) для треков, к которым давно не обращались."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT youtube_id, cached_path FROM tracks WHERE cached_path IS NOT NULL AND last_accessed < ?",
            (cutoff_timestamp,),
        )
        return await cursor.fetchall()


async def clear_cached_path(youtube_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tracks SET cached_path = NULL WHERE youtube_id = ?", (youtube_id,))
        await db.commit()
