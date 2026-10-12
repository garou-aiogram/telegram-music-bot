# Music Search Bot — inline-поиск музыки в Telegram

Набираешь `@твойбот запрос` в любом чате → выпадает список треков → жмёшь →
приходит готовый mp3. Без Mini App, без фронтенда, без ngrok — только бот.

## 1. Ключи

Те же, что и раньше:
- **BOT_TOKEN** — от [@BotFather](https://t.me/BotFather) (`/newbot`, если ещё нет)
- **YOUTUBE_API_KEY** — из [Google Cloud Console](https://console.cloud.google.com/)
  (APIs & Services → Library → YouTube Data API v3 → Enable → Credentials → Create API key)

## 2. Включи inline-режим у бота

Это обязательный шаг, без него `@твойбот запрос` не заработает вообще.

1. Напиши [@BotFather](https://t.me/BotFather) → `/mybots` → выбери своего бота
2. **Bot Settings → Inline Mode → Turn on**
3. Появится запрос на **placeholder text** — текст, который виден в поле ввода
   до того как ты начал печатать запрос. Напиши что-то вроде:
   `Введите название трека…`

## 3. Установка ffmpeg

```bash
ffmpeg -version
```
Если команда не находится — поставь (Windows: скачать с ffmpeg.org и добавить в PATH;
Linux: `sudo apt install ffmpeg`; macOS: `brew install ffmpeg`).

## 4. Запуск

```bash
cd inline_bot
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env        # Windows
# cp .env.example .env        # Linux/Mac
```

Открой `.env` и впиши реальные `BOT_TOKEN` и `YOUTUBE_API_KEY` вместо заглушек.

```bash
python main.py
```

Если всё ок — в терминале появится `Start polling` и никаких ошибок.

## 5. Проверка

Открой Telegram → любой чат (можно даже "Избранное"/Saved Messages) → в поле
ввода набери:
```
@твой_бот выше
```
(замени `твой_бот` на настоящий username бота). Должен появиться всплывающий
список треков над клавиатурой. Тапни на один — в чат придёт сообщение с
плейсхолдером "⏳ Загружаю…", которое через несколько секунд само заменится
на готовый аудиофайл.

## Как это устроено (для отчёта/защиты)

1. **Поиск** (`app/youtube.py`) — запрос к официальному YouTube Data API v3,
   возвращает только метаданные (название, канал, превью, длительность).
2. **Inline-запрос** (`app/handlers.py:handle_inline_query`) — Telegram шлёт
   боту текст, который набрали после `@bot`; бот отвечает списком
   `InlineQueryResultArticle` с прикреплённой inline-клавиатурой (плейсхолдер
   кнопка) — именно из-за этой клавиатуры Telegram потом присылает
   `inline_message_id`, без которого нельзя отредактировать сообщение позже.
3. **Выбор результата** (`handle_chosen_inline_result`) — как только пользователь
   тапает на трек, Telegram шлёт update `chosen_inline_result` с id трека и
   `inline_message_id`. Бот скачивает аудио через yt-dlp+ffmpeg (или берёт из
   кэша, если уже скачивали) и вызывает `edit_message_media`, заменяя
   текстовый плейсхолдер на реальный аудиофайл — прямо в том же сообщении,
   без отправки нового.
4. **Кэш** (`app/db.py`, `app/cache.py`) — SQLite хранит путь к уже скачанным
   файлам; APScheduler раз в час чистит файлы, к которым давно не обращались.

## Важное замечание

Проект — для личного/учебного использования. Массовая раздача чужой музыки
через скачивание с YouTube нарушает условия использования YouTube и авторские
права. Не разворачивай это как публичный сервис для посторонних пользователей.
