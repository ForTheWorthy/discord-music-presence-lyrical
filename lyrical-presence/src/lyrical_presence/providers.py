from __future__ import annotations

import json
import logging
import re
import time
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
MUSIXMATCH_ROOT = "https://apic-desktop.musixmatch.com/ws/1.1/"
MUSIXMATCH_APP_ID = "web-desktop-app-v1.0"


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


class MusixmatchClient:
    """Synced lyrics from Musixmatch (same catalog Apple Music uses).

    Uses the Musixmatch desktop web API endpoints commonly used by open-source
    lyric tools. Optionally accepts a user token via config/env for stability.
    """

    name = "musixmatch"

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 12.0,
        user_token: str | None = None,
        token_cache_path: Path | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.user_token = user_token
        self.token_cache_path = token_cache_path or (
            Path.home() / ".cache" / "lyrical-presence" / "musixmatch_token.json"
        )
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Cookie", "AWSELB=0")

    def fetch_for_track(self, track: Track) -> Lyrics | None:
        track = normalize_track(track)
        track_id = self._search_track_id(track)
        if track_id is None:
            return None
        synced = self._fetch_subtitle_lrc(track_id)
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

    def _search_track_id(self, track: Track) -> int | None:
        queries: list[str] = []
        for title in search_title_variants(track.title):
            queries.append(f"{title} {track.artist}")
            if track.album:
                queries.append(f"{title} {track.artist} {track.album}")
        seen: set[str] = set()
        for query in queries:
            query = " ".join(query.split()).strip()
            if not query or query.lower() in seen:
                continue
            seen.add(query.lower())
            track_id = self._search_once(query, track)
            if track_id is not None:
                return track_id
        return None

    def _search_once(self, query: str, track: Track) -> int | None:
        data = self._api(
            "track.search",
            [
                ("q", query),
                ("page_size", "8"),
                ("page", "1"),
                ("f_has_subtitle", "1"),
            ],
        )
        if not data:
            return None
        header = data.get("message", {}).get("header", {})
        if header.get("status_code") != 200:
            log.debug("Musixmatch search status %s", header.get("status_code"))
            return None
        body = data.get("message", {}).get("body")
        if not isinstance(body, dict):
            return None
        tracks = body.get("track_list")
        if not isinstance(tracks, list) or not tracks:
            return None
        scored = sorted(
            (item for item in tracks if isinstance(item, dict) and "track" in item),
            key=lambda item: self._score(item["track"], track),
            reverse=True,
        )
        if not scored or self._score(scored[0]["track"], track) <= 0:
            return None
        track_id = scored[0]["track"].get("track_id")
        return int(track_id) if isinstance(track_id, int) else None

    def _fetch_subtitle_lrc(self, track_id: int) -> str | None:
        data = self._api(
            "track.subtitle.get",
            [("track_id", str(track_id)), ("subtitle_format", "lrc")],
        )
        if not data:
            return None
        body = data.get("message", {}).get("body")
        if not isinstance(body, dict):
            return None
        subtitle = body.get("subtitle")
        if not isinstance(subtitle, dict):
            return None
        text = str(subtitle.get("subtitle_body") or "").strip()
        return text or None

    def _api(self, action: str, params: list[tuple[str, str]]) -> dict[str, Any] | None:
        token = self._ensure_token()
        if token is None and action != "token.get":
            return None
        query = list(params)
        query.append(("app_id", MUSIXMATCH_APP_ID))
        if token:
            query.append(("usertoken", token))
        query.append(("t", str(int(time.time() * 1000))))
        try:
            response = self.session.get(
                MUSIXMATCH_ROOT + action,
                params=query,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Musixmatch %s failed: %s", action, exc)
            return None
        if not response.ok:
            log.debug("Musixmatch %s HTTP %s", action, response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def _ensure_token(self) -> str | None:
        if self.user_token:
            return self.user_token
        cached = self._read_cached_token()
        if cached:
            return cached
        data = self._api("token.get", [("user_language", "en")])
        if not data:
            return None
        header = data.get("message", {}).get("header", {})
        status = header.get("status_code")
        if status == 401:
            log.warning("Musixmatch token rate-limited; retry later")
            return None
        body = data.get("message", {}).get("body")
        if not isinstance(body, dict):
            return None
        token = str(body.get("user_token") or "").strip()
        if not token:
            return None
        self.user_token = token
        self._write_cached_token(token)
        return token

    def _read_cached_token(self) -> str | None:
        path = self.token_cache_path
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        token = str(payload.get("token") or "").strip()
        expires = payload.get("expiration_time")
        if not token:
            return None
        if isinstance(expires, (int, float)) and time.time() >= float(expires):
            return None
        self.user_token = token
        return token

    def _write_cached_token(self, token: str) -> None:
        path = self.token_cache_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "token": token,
                        "expiration_time": int(time.time()) + 600,
                    }
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            log.debug("Could not cache Musixmatch token: %s", exc)

    @staticmethod
    def _score(item: dict[str, Any], track: Track) -> int:
        score = 0
        title = str(item.get("track_name") or "").strip().lower()
        artist = str(item.get("artist_name") or "").strip().lower()
        album = str(item.get("album_name") or "").strip().lower()
        duration = item.get("track_length")
        has_lyrics = item.get("has_lyrics") or item.get("has_subtitles")

        title_variants = {t.lower() for t in search_title_variants(track.title)}
        if title in title_variants:
            score += 5
        elif any(t in title or title in t for t in title_variants):
            score += 2

        artist_q = track.artist.strip().lower()
        if artist_q and artist:
            if artist == artist_q or artist_q in artist or artist in artist_q:
                score += 5

        if track.album and album:
            if album == track.album.strip().lower():
                score += 3
            elif track.album.strip().lower() in album:
                score += 1

        if track.duration_seconds and isinstance(duration, (int, float)):
            delta = abs(float(duration) - float(track.duration_seconds))
            if delta <= 2:
                score += 4
            elif delta <= 5:
                score += 2
            elif delta > 25:
                score -= 3

        if has_lyrics:
            score += 1
        return score


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


def build_default_fetcher(
    lyrics_dir: Path | None = None,
    *,
    musixmatch_token: str | None = None,
) -> LyricsFetcher:
    directory = lyrics_dir if lyrics_dir is not None else default_lyrics_dir()
    return LyricsFetcher(
        [
            LocalLrcProvider(directory),
            MusixmatchClient(user_token=musixmatch_token),
            LrclibClient(),
            NetEaseClient(),
        ]
    )
