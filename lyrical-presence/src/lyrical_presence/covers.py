from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

import requests

from lyrical_presence import __version__
from lyrical_presence.models import Track

log = logging.getLogger(__name__)

USER_AGENT = (
    f"LyricalPresence/{__version__} "
    "(https://github.com/ForTheWorthy/discord-music-presence-lyrical)"
)
_ITUNES_SIZE = re.compile(r"\d+x\d+(?=bb\.)")


class CoverArtClient:
    """Resolve a public HTTPS album-cover URL for Discord Rich Presence."""

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 10.0,
        artwork_size: int = 600,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.artwork_size = artwork_size
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self._cache: dict[tuple[str, str, str], str | None] = {}

    def cover_url_for(self, track: Track) -> str | None:
        identity = track.identity
        if identity in self._cache:
            return self._cache[identity]

        url = self._search_itunes(track)
        self._cache[identity] = url
        if url:
            log.info("Album cover: %s", url)
        else:
            log.info("No album cover found for %s — %s", track.artist, track.title)
        return url

    def _search_itunes(self, track: Track) -> str | None:
        queries = [
            " ".join(part for part in [track.artist, track.album, track.title] if part),
            " ".join(part for part in [track.artist, track.title] if part),
            " ".join(part for part in [track.artist, track.album] if part),
        ]
        seen: set[str] = set()
        for query in queries:
            query = " ".join(query.split()).strip()
            if not query or query.lower() in seen:
                continue
            seen.add(query.lower())
            result = self._itunes_lookup(query, track)
            if result:
                return result
        return None

    def _itunes_lookup(self, term: str, track: Track) -> str | None:
        url = f"https://itunes.apple.com/search?term={quote_plus(term)}&media=music&limit=5"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            log.warning("iTunes cover lookup failed: %s", exc)
            return None
        if not response.ok:
            log.warning("iTunes cover lookup HTTP %s", response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or not results:
            return None

        scored = sorted(
            (item for item in results if isinstance(item, dict)),
            key=lambda item: self._score(item, track),
            reverse=True,
        )
        if not scored or self._score(scored[0], track) <= 0:
            return None
        artwork = str(scored[0].get("artworkUrl100") or "").strip()
        if not artwork:
            return None
        return self._upsample(artwork)

    def _upsample(self, artwork_url: str) -> str:
        size = max(int(self.artwork_size), 100)
        if _ITUNES_SIZE.search(artwork_url):
            return _ITUNES_SIZE.sub(f"{size}x{size}", artwork_url)
        return artwork_url.replace("100x100", f"{size}x{size}")

    @staticmethod
    def _score(item: dict[str, Any], track: Track) -> int:
        score = 0
        track_name = str(item.get("trackName") or item.get("collectionName") or "").lower()
        artist = str(item.get("artistName") or "").lower()
        album = str(item.get("collectionName") or "").lower()

        title_q = track.title.strip().lower()
        artist_q = track.artist.strip().lower()
        album_q = track.album.strip().lower()

        if artist and artist_q:
            if artist == artist_q:
                score += 5
            elif artist_q in artist or artist in artist_q:
                score += 2

        if title_q and track_name:
            if title_q == track_name or title_q in track_name or track_name in title_q:
                score += 4

        if album_q and album:
            if album == album_q:
                score += 4
            elif album_q in album or album in album_q:
                score += 2

        if item.get("artworkUrl100"):
            score += 1
        return score
