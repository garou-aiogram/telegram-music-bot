import re

import httpx

from app.config import YOUTUBE_API_KEY

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _parse_duration(iso_duration: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


async def search_tracks(query: str, max_results: int = 12) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        search_resp = await client.get(
            YOUTUBE_SEARCH_URL,
            params={
                "key": YOUTUBE_API_KEY,
                "q": query,
                "part": "snippet",
                "type": "video",
                "videoCategoryId": "10",
                "maxResults": max_results,
            },
        )
        search_resp.raise_for_status()
        items = search_resp.json().get("items", [])
        video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]

        if not video_ids:
            return []

        details_resp = await client.get(
            YOUTUBE_VIDEOS_URL,
            params={"key": YOUTUBE_API_KEY, "id": ",".join(video_ids), "part": "contentDetails"},
        )
        details_resp.raise_for_status()
        durations = {
            item["id"]: _parse_duration(item["contentDetails"]["duration"])
            for item in details_resp.json().get("items", [])
        }

    results = []
    for item in items:
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item["snippet"]
        results.append(
            {
                "youtube_id": video_id,
                "title": snippet["title"],
                "artist": snippet["channelTitle"],
                "duration_seconds": durations.get(video_id, 0),
                "thumbnail_url": snippet["thumbnails"]["high"]["url"],
            }
        )
    return results
