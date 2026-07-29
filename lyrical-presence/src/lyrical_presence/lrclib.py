from __future__ import annotations

import logging
from typing import Any

import requests

from lyrical_presence import __version__
from lyrical_presence.lrc import parse_lrc
from lyrical_presence.models import Lyrics, Track

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://lrclib.net"
USER_AGENT = (
    f"LyricalPresence/{__version__} "
    "(https://github.com/ForTheWorthy/discord-music-presence-lyrical)"
)


class LrclibClient:
    """Client for the free LRCLIB synced-lyrics API."""

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
        lyrics = self._get_exact(track)
        if lyrics is not None:
            return lyrics
        return self._search_best(track)

    def _get_exact(self, track: Track) -> Lyrics | None:
        if track.duration_seconds is None or track.duration_seconds <= 0:
            return None
        params = {
            "track_name": track.title,
            "artist_name": track.artist,
            "album_name": track.album or track.title,
            "duration": int(round(track.duration_seconds)),
        }
        try:
            response = self.session.get(
                f"{self.base_url}/api/get",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("LRCLIB exact lookup failed: %s", exc)
            return None

        if response.status_code == 404:
            return None
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "?")
            log.warning("LRCLIB rate limited; retry after %s seconds", retry_after)
            return None
        if not response.ok:
            log.warning("LRCLIB exact lookup HTTP %s", response.status_code)
            return None
        return self._parse_record(response.json())

    def _search_best(self, track: Track) -> Lyrics | None:
        params = {
            "track_name": track.title,
            "artist_name": track.artist,
        }
        if track.album:
            params["album_name"] = track.album
        try:
            response = self.session.get(
                f"{self.base_url}/api/search",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("LRCLIB search failed: %s", exc)
            return None

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "?")
            log.warning("LRCLIB rate limited; retry after %s seconds", retry_after)
            return None
        if not response.ok:
            log.warning("LRCLIB search HTTP %s", response.status_code)
            return None

        results = response.json()
        if not isinstance(results, list) or not results:
            return None

        scored = sorted(
            results,
            key=lambda item: self._score_result(item, track),
            reverse=True,
        )
        best = scored[0]
        if self._score_result(best, track) <= 0:
            return None
        return self._parse_record(best)

    @staticmethod
    def _score_result(item: dict[str, Any], track: Track) -> int:
        score = 0
        title = str(item.get("trackName") or "").strip().lower()
        artist = str(item.get("artistName") or "").strip().lower()
        album = str(item.get("albumName") or "").strip().lower()
        duration = item.get("duration")

        if title == track.title.strip().lower():
            score += 5
        elif track.title.strip().lower() in title or title in track.title.strip().lower():
            score += 2

        if artist == track.artist.strip().lower():
            score += 5
        elif track.artist.strip().lower() in artist or artist in track.artist.strip().lower():
            score += 2

        if track.album and album == track.album.strip().lower():
            score += 2

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
