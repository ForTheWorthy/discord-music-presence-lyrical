from __future__ import annotations

import logging
import time
from typing import Any

import requests

from lyrical_presence import __version__
from lyrical_presence.lrc import parse_lrc
from lyrical_presence.models import Lyrics, Track
from lyrical_presence.normalize import normalize_track, search_title_variants

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://lrclib.net"
USER_AGENT = (
    f"LyricalPresence/{__version__} "
    "(https://github.com/ForTheWorthy/discord-music-presence-lyrical)"
)


class LrclibClient:
    """Client for the free LRCLIB synced-lyrics API."""

    name = "lrclib"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch_for_track(self, track: Track) -> Lyrics | None:
        """Fetch lyrics for a track, preferring an exact signature match."""
        track = normalize_track(track)
        lyrics = self._get_exact(track)
        if lyrics is not None:
            return lyrics
        return self._search_best(track)

    def _get_exact(self, track: Track) -> Lyrics | None:
        if track.duration_seconds is None or track.duration_seconds <= 0:
            return None
        for title in search_title_variants(track.title):
            params = {
                "track_name": title,
                "artist_name": track.artist,
                "album_name": track.album or title,
                "duration": int(round(track.duration_seconds)),
            }
            data = self._get_json("/api/get", params, allow_404=True)
            if data is None:
                continue
            return self._parse_record(data)
        return None

    def _search_best(self, track: Track) -> Lyrics | None:
        candidates: list[dict[str, Any]] = []
        seen_ids: set[Any] = set()

        for title in search_title_variants(track.title):
            params: dict[str, Any] = {
                "track_name": title,
                "artist_name": track.artist,
            }
            if track.album:
                params["album_name"] = track.album
            self._extend_candidates(candidates, seen_ids, self._search(params))
            # Brief pause between LRCLIB requests (API guidance).
            time.sleep(0.2)

        if not candidates:
            query = " ".join(part for part in [track.title, track.artist, track.album] if part)
            self._extend_candidates(
                candidates,
                seen_ids,
                self._search({"q": query}),
            )

        if not candidates:
            return None

        scored = sorted(
            candidates,
            key=lambda item: self._score_result(item, track),
            reverse=True,
        )
        best = scored[0]
        best_score = self._score_result(best, track)
        if best_score <= 0:
            log.debug("Best LRCLIB match scored too low (%s): %s", best_score, best)
            return None
        return self._parse_record(best)

    def _search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._get_json("/api/search", params, allow_404=False)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _get_json(
        self,
        path: str,
        params: dict[str, Any],
        *,
        allow_404: bool,
    ) -> Any | None:
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("LRCLIB request failed (%s): %s", path, exc)
            return None

        if response.status_code == 404 and allow_404:
            return None
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "?")
            log.warning("LRCLIB rate limited; retry after %s seconds", retry_after)
            return None
        if not response.ok:
            log.warning("LRCLIB %s HTTP %s", path, response.status_code)
            return None
        return response.json()

    @staticmethod
    def _extend_candidates(
        candidates: list[dict[str, Any]],
        seen_ids: set[Any],
        items: list[dict[str, Any]],
    ) -> None:
        for item in items:
            item_id = item.get("id")
            key = item_id if item_id is not None else (
                item.get("trackName"),
                item.get("artistName"),
                item.get("albumName"),
                item.get("duration"),
            )
            if key in seen_ids:
                continue
            seen_ids.add(key)
            candidates.append(item)

    @staticmethod
    def _score_result(item: dict[str, Any], track: Track) -> int:
        score = 0
        title = str(item.get("trackName") or "").strip().lower()
        artist = str(item.get("artistName") or "").strip().lower()
        album = str(item.get("albumName") or "").strip().lower()
        duration = item.get("duration")

        track_titles = {t.lower() for t in search_title_variants(track.title)}
        if title in track_titles:
            score += 5
        elif any(t in title or title in t for t in track_titles):
            score += 2

        artist_query = track.artist.strip().lower()
        if artist == artist_query:
            score += 5
        elif artist_query in artist or artist in artist_query:
            score += 2

        if track.album and album == track.album.strip().lower():
            score += 3
        elif track.album and track.album.strip().lower() in album:
            score += 1

        if track.duration_seconds and isinstance(duration, (int, float)):
            delta = abs(float(duration) - float(track.duration_seconds))
            if delta <= 2:
                score += 4
            elif delta <= 5:
                score += 2
            elif delta > 20:
                score -= 3

        if item.get("syncedLyrics"):
            score += 3
        if item.get("instrumental"):
            score -= 1
        return score

    @staticmethod
    def _parse_record(data: dict[str, Any]) -> Lyrics:
        synced = parse_lrc(data.get("syncedLyrics"))
        return Lyrics(
            track_name=str(data.get("trackName") or ""),
            artist_name=str(data.get("artistName") or ""),
            album_name=str(data.get("albumName") or ""),
            duration=float(data["duration"]) if data.get("duration") is not None else None,
            instrumental=bool(data.get("instrumental")),
            synced_lines=synced,
            plain_lyrics=str(data.get("plainLyrics") or ""),
        )
