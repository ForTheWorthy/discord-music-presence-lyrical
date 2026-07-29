from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import requests

from lyrical_presence import __version__
from lyrical_presence.lrc import parse_lrc
from lyrical_presence.lrclib import LrclibClient
from lyrical_presence.models import Lyrics, Track
from lyrical_presence.normalize import normalize_track, search_title_variants

log = logging.getLogger(__name__)

USER_AGENT = (
    f"LyricalPresence/{__version__} "
    "(https://github.com/ForTheWorthy/discord-music-presence-lyrical)"
)
_SAFE_NAME = re.compile(r'[<>:"/\\|?*]')


class LyricsProvider(Protocol):
    name: str

    def fetch_for_track(self, track: Track) -> Lyrics | None: ...


class LocalLrcProvider:
    """Load synced lyrics from a local folder of .lrc files."""

    name = "local"

    def __init__(self, lyrics_dir: Path | None = None) -> None:
        self.lyrics_dir = lyrics_dir

    def fetch_for_track(self, track: Track) -> Lyrics | None:
        if self.lyrics_dir is None or not self.lyrics_dir.is_dir():
            return None
        track = normalize_track(track)
        for candidate in self._candidates(track):
            path = self.lyrics_dir / candidate
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning("Failed reading %s: %s", path, exc)
                continue
            lines = parse_lrc(text)
            if not lines:
                continue
            log.info("Loaded local lyrics from %s", path.name)
            return Lyrics(
                track_name=track.title,
                artist_name=track.artist,
                album_name=track.album,
                duration=track.duration_seconds,
                instrumental=False,
                synced_lines=lines,
                plain_lyrics=text,
            )
        return None

    def _candidates(self, track: Track) -> list[str]:
        names: list[str] = []
        for title in search_title_variants(track.title):
            names.extend(
                [
                    f"{track.artist} - {title}.lrc",
                    f"{title} - {track.artist}.lrc",
                    f"{title}.lrc",
                ]
            )
        # Deduplicate while preserving order.
        seen: set[str] = set()
        result: list[str] = []
        for name in names:
            safe = _SAFE_NAME.sub("", name).strip()
            key = safe.lower()
            if not safe or key in seen:
                continue
            seen.add(key)
            result.append(safe)
        return result


class NetEaseClient:
    """Synced lyrics fallback via NetEase Cloud Music search API."""

    name = "netease"

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 12.0,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Referer", "https://music.163.com/")

    def fetch_for_track(self, track: Track) -> Lyrics | None:
        track = normalize_track(track)
        song_id = self._search_song_id(track)
        if song_id is None:
            return None
        synced = self._fetch_lrc(song_id)
        if not synced:
            return None
        lines = parse_lrc(synced)
        if not lines:
            return None
        return Lyrics(
            track_name=track.title,
            artist_name=track.artist,
            album_name=track.album,
            duration=track.duration_seconds,
            instrumental=False,
            synced_lines=lines,
            plain_lyrics=synced,
        )

    def _search_song_id(self, track: Track) -> int | None:
        queries = []
        for title in search_title_variants(track.title):
            queries.append(f"{track.artist} {title}")
            queries.append(title)
        seen: set[str] = set()
        for query in queries:
            query = " ".join(query.split()).strip()
            if not query or query.lower() in seen:
                continue
            seen.add(query.lower())
            song_id = self._search_once(query, track)
            if song_id is not None:
                return song_id
        return None

    def _search_once(self, query: str, track: Track) -> int | None:
        url = (
            "https://music.163.com/api/search/get/web"
            f"?s={quote(query)}&type=1&offset=0&total=true&limit=8"
        )
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            log.warning("NetEase search failed: %s", exc)
            return None
        if not response.ok:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        songs = (
            payload.get("result", {}).get("songs")
            if isinstance(payload, dict)
            else None
        )
        if not isinstance(songs, list) or not songs:
            return None

        scored = sorted(
            (song for song in songs if isinstance(song, dict)),
            key=lambda song: self._score(song, track),
            reverse=True,
        )
        if not scored or self._score(scored[0], track) <= 0:
            return None
        song_id = scored[0].get("id")
        return int(song_id) if isinstance(song_id, int) else None

    def _fetch_lrc(self, song_id: int) -> str | None:
        url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=-1&tv=-1"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            log.warning("NetEase lyric fetch failed: %s", exc)
            return None
        if not response.ok:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        lrc = payload.get("lrc") if isinstance(payload, dict) else None
        if not isinstance(lrc, dict):
            return None
        lyric = str(lrc.get("lyric") or "").strip()
        return lyric or None

    @staticmethod
    def _score(song: dict[str, Any], track: Track) -> int:
        score = 0
        name = str(song.get("name") or "").strip().lower()
        artists = song.get("artists") if isinstance(song.get("artists"), list) else []
        artist_names = " ".join(
            str(artist.get("name") or "") for artist in artists if isinstance(artist, dict)
        ).lower()
        album_obj = song.get("album") if isinstance(song.get("album"), dict) else {}
        album = str(album_obj.get("name") or "").lower()
        duration_ms = song.get("duration")

        title_variants = {t.lower() for t in search_title_variants(track.title)}
        if name in title_variants:
            score += 5
        elif any(t in name or name in t for t in title_variants):
            score += 2

        artist_q = track.artist.strip().lower()
        if artist_q and artist_names:
            if artist_q == artist_names or artist_q in artist_names:
                score += 5
            elif any(part and part in artist_names for part in artist_q.replace(",", " ").split()):
                score += 2

        if track.album and album:
            if track.album.strip().lower() == album:
                score += 3
            elif track.album.strip().lower() in album:
                score += 1

        if track.duration_seconds and isinstance(duration_ms, (int, float)):
            delta = abs((duration_ms / 1000.0) - float(track.duration_seconds))
            if delta <= 2:
                score += 4
            elif delta <= 5:
                score += 2
            elif delta > 25:
                score -= 3
        return score


class LyricsFetcher:
    """Try multiple lyrics sources until synced lyrics are found."""

    def __init__(self, providers: list[LyricsProvider]) -> None:
        self.providers = providers

    def fetch_for_track(self, track: Track) -> Lyrics | None:
        track = normalize_track(track)
        for provider in self.providers:
            try:
                lyrics = provider.fetch_for_track(track)
            except Exception as exc:  # noqa: BLE001 - one provider must not kill the chain
                log.warning("Lyrics provider %s failed: %s", getattr(provider, "name", provider), exc)
                continue
            if lyrics is None:
                log.debug("Provider %s: no lyrics", getattr(provider, "name", provider))
                continue
            if lyrics.instrumental:
                log.info("Provider %s: instrumental", getattr(provider, "name", provider))
                return lyrics
            if lyrics.has_synced:
                log.info(
                    "Provider %s: %d synced lines",
                    getattr(provider, "name", provider),
                    len(lyrics.synced_lines),
                )
                return lyrics
            log.debug(
                "Provider %s: lyrics without sync timestamps, continuing",
                getattr(provider, "name", provider),
            )
        return None


def default_lyrics_dir() -> Path:
    if Path.home().joinpath("AppData", "Roaming").exists():
        return Path.home() / "AppData" / "Roaming" / "Lyrical Presence" / "lyrics"
    return Path.home() / ".config" / "lyrical-presence" / "lyrics"


def build_default_fetcher(lyrics_dir: Path | None = None) -> LyricsFetcher:
    directory = lyrics_dir if lyrics_dir is not None else default_lyrics_dir()
    return LyricsFetcher(
        [
            LocalLrcProvider(directory),
            LrclibClient(),
            NetEaseClient(),
        ]
    )
