from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from lyrical_presence.discord_rpc import DiscordPresence
from lyrical_presence.lrc import line_at
from lyrical_presence.lrclib import LrclibClient
from lyrical_presence.media import MediaBackend
from lyrical_presence.models import Lyrics, Track

log = logging.getLogger(__name__)


@dataclass
class SyncConfig:
    poll_interval_seconds: float = 0.75
    clear_on_pause: bool = False
    show_progress: bool = True
    paused_lyric_prefix: str = "⏸ "


class LyricPresenceService:
    """Poll media playback, fetch lyrics, and push the active line to Discord."""

    def __init__(
        self,
        media: MediaBackend,
        lyrics_client: LrclibClient,
        presence: DiscordPresence,
        config: SyncConfig | None = None,
    ) -> None:
        self.media = media
        self.lyrics_client = lyrics_client
        self.presence = presence
        self.config = config or SyncConfig()
        self._lyrics_cache: dict[tuple[str, str, str], Lyrics | None] = {}
        self._current_identity: tuple[str, str, str] | None = None
        self._last_lyric_text: str | None = None
        self._running = False

    def run_forever(self) -> None:
        self.presence.connect()
        self._running = True
        log.info("Lyrical Presence is running (poll every %.2fs)", self.config.poll_interval_seconds)
        try:
            while self._running:
                self.tick()
                time.sleep(self.config.poll_interval_seconds)
        except KeyboardInterrupt:
            log.info("Interrupted, shutting down")
        finally:
            self.presence.close()

    def stop(self) -> None:
        self._running = False

    def tick(self) -> None:
        track = self.media.current_track()
        if track is None or not track.is_valid():
            if self._current_identity is not None:
                self.presence.clear()
                self._current_identity = None
                self._last_lyric_text = None
            return

        if not track.playing and self.config.clear_on_pause:
            self.presence.clear()
            self._last_lyric_text = None
            return

        identity = track.identity
        if identity != self._current_identity:
            self._current_identity = identity
            self._last_lyric_text = None
            log.info("Now playing: %s — %s", track.artist, track.title)

        lyrics = self._lyrics_for(track)
        lyric_text = self._active_lyric_text(track, lyrics)
        if lyric_text is None:
            self.presence.update_fallback(track, show_progress=self.config.show_progress)
            self._last_lyric_text = None
            return

        if not track.playing:
            lyric_text = f"{self.config.paused_lyric_prefix}{lyric_text}"

        if lyric_text != self._last_lyric_text:
            log.info("Lyric: %s", lyric_text)
            self._last_lyric_text = lyric_text
        self.presence.update_lyrics(
            track,
            lyric_text,
            show_progress=self.config.show_progress,
        )

    def _lyrics_for(self, track: Track) -> Lyrics | None:
        identity = track.identity
        if identity in self._lyrics_cache:
            return self._lyrics_cache[identity]
        log.info("Fetching lyrics for %s — %s", track.artist, track.title)
        lyrics = self.lyrics_client.fetch_for_track(track)
        self._lyrics_cache[identity] = lyrics
        if lyrics is None:
            log.info("No lyrics found")
        elif lyrics.instrumental:
            log.info("Track is instrumental")
        elif lyrics.has_synced:
            log.info("Loaded %d synced lyric lines", len(lyrics.synced_lines))
        else:
            log.info("Only plain lyrics available; timed line sync disabled")
        return lyrics

    @staticmethod
    def _active_lyric_text(track: Track, lyrics: Lyrics | None) -> str | None:
        if lyrics is None or lyrics.instrumental or not lyrics.has_synced:
            return None
        line = line_at(lyrics.synced_lines, track.position_seconds)
        if line is None:
            return None
        return line.text
