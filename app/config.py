import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
CACHE_TTL_HOURS = int(os.environ.get("CACHE_TTL_HOURS", "48"))
# Твой личный Telegram user ID (узнать через @userinfobot) — бот шлёт сюда
# первую копию каждого скачанного трека, чтобы получить его file_id и потом
# редактировать inline-сообщения без повторной загрузки файла с диска.
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "storage" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = BASE_DIR / "storage" / "tracks.sqlite3"
