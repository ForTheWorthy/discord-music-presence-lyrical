from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from lyrical_presence.clock import PlaybackClock
from lyrical_presence.covers import CoverArtClient
from lyrical_presence.discord_rpc import DiscordPresence
from lyrical_presence.lrc import line_window
from lyrical_presence.media import MediaBackend
from lyrical_presence.models import Lyrics, Track
from lyrical_presence.normalize import normalize_track
from lyrical_presence.providers import LyricsFetcher, build_default_fetcher
from lyrical_presence.symbols import DEFAULT_MUSIC_SYMBOLS, format_music_only

log = logging.getLogger(__name__)


@dataclass
class SyncConfig:
    # Detect line changes often.
    poll_interval_seconds: float = 0.1
    clear_on_pause: bool = False
    show_progress: bool = True
    paused_lyric_prefix: str = "⏸ "
    show_music_symbols: bool = True
    music_symbols: tuple[str, ...] = field(default_factory=lambda: DEFAULT_MUSIC_SYMBOLS)
    music_symbol_interval_seconds: float = 9999.0
    music_symbol_repeat: int = 3
    # Modest lead: enough for Discord latency, low enough not to jump short lines.
    lyric_lead_seconds: float = 0.25
    show_album_cover: bool = True
    # Cap how fast we push to Discord (short-line songs enqueue; we drain safely).
    # ~1.0s is aggressive enough to show most lines; raise toward 1.5 if Discord
    # starts rejecting updates on your account.
    discord_min_interval_seconds: float = 1.0
    # If we fall behind, keep only the newest N queued lines.
    discord_max_queue: int = 12


class LyricPresenceService:
    """Poll media playback, queue lyric lines, and push them to Discord at a safe rate."""

    def __init__(
        self,
        media: MediaBackend,
        presence: DiscordPresence,
        config: SyncConfig | None = None,
        cover_client: CoverArtClient | None = None,
        lyrics_fetcher: LyricsFetcher | None = None,
        # Back-compat for tests that pass a single provider-like client.
        lyrics_client: Any | None = None,
    ) -> None:
        self.media = media
        self.presence = presence
        self.config = config or SyncConfig()
        self.cover_client = cover_client or CoverArtClient()
        if lyrics_fetcher is not None:
            self.lyrics_fetcher = lyrics_fetcher
        elif lyrics_client is not None:
            self.lyrics_fetcher = LyricsFetcher([lyrics_client])
        else:
            self.lyrics_fetcher = build_default_fetcher()
        self._lyrics_cache: dict[tuple[str, str, str], Lyrics | None] = {}
        self._cover_cache: dict[tuple[str, str, str], str | None] = {}
        self._current_identity: tuple[str, str, str] | None = None
        self._last_detected_lyric: str | None = None
        self._pending_lyrics: list[str] = []
        self._last_sent_lyric: str | None = None
        self._last_sent_at = 0.0
        self._running = False
        self._clock = PlaybackClock()
        self._current_track: Track | None = None

    def run_forever(self) -> None:
        self.presence.connect()
        self._running = True
        log.info(
            "Lyrical Presence is running (poll every %.2fs, Discord min interval %.2fs)",
            self.config.poll_interval_seconds,
            self.config.discord_min_interval_seconds,
        )
        try:
            while self._running:
                started = time.monotonic()
                self.tick()
                elapsed = time.monotonic() - started
                delay = self.config.poll_interval_seconds - elapsed
                if delay > 0:
                    time.sleep(delay)
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
                self._reset_lyric_pipeline()
                self._current_identity = None
            return

        track = self._clock.resolve(normalize_track(track))
        self._current_track = track

        if not track.playing and self.config.clear_on_pause:
            self.presence.clear()
            self._reset_lyric_pipeline()
            return

        identity = track.identity
        if identity != self._current_identity:
            self._current_identity = identity
            self._reset_lyric_pipeline()
            log.info("Now playing: %s — %s", track.artist, track.title)

        lyrics = self._lyrics_for(track)
        lookup_track = self._with_lyric_lead(track)
        lyric_text = self._presence_text(lookup_track, lyrics)

        if not track.playing:
            lyric_text = f"{self.config.paused_lyric_prefix}{lyric_text}"

        self._enqueue_lyric(lyric_text)
        self._flush_queue()

    def _reset_lyric_pipeline(self) -> None:
        self._last_detected_lyric = None
        self._pending_lyrics.clear()
        self._last_sent_lyric = None
        self._last_sent_at = 0.0

    def _enqueue_lyric(self, lyric_text: str) -> None:
        if lyric_text == self._last_detected_lyric:
            log.debug("[pipeline] lyric unchanged, not queued: %s", lyric_text)
            return
        self._last_detected_lyric = lyric_text
        if self._pending_lyrics and self._pending_lyrics[-1] == lyric_text:
            log.debug("[pipeline] lyric already at tail of queue: %s", lyric_text)
            return
        self._pending_lyrics.append(lyric_text)
        log.info("[pipeline] queued (%d waiting): %s", len(self._pending_lyrics), lyric_text)

        max_queue = max(1, self.config.discord_max_queue)
        if len(self._pending_lyrics) > max_queue:
            dropped = len(self._pending_lyrics) - max_queue
            self._pending_lyrics = self._pending_lyrics[-max_queue:]
            log.debug(
                "[pipeline] dropped %d oldest queued lyrics to limit backlog",
                dropped,
            )

    def _flush_queue(self) -> None:
        track = self._current_track
        if track is None:
            return

        now = time.monotonic()
        min_interval = max(0.0, self.config.discord_min_interval_seconds)
        if self._last_sent_lyric is not None and (now - self._last_sent_at) < min_interval:
            if self._pending_lyrics:
                remaining = min_interval - (now - self._last_sent_at)
                log.debug(
                    "[pipeline] waiting for cadence (%.2fs left, %d queued)",
                    remaining,
                    len(self._pending_lyrics),
                )
            return

        while self._pending_lyrics:
            lyric_text = self._pending_lyrics.pop(0)
            if lyric_text == self._last_sent_lyric:
                log.debug("[pipeline] skip duplicate already sent: %s", lyric_text)
                continue

            cover_url = None
            if self.config.show_album_cover:
                identity = track.identity
                if identity not in self._cover_cache:
                    self._cover_cache[identity] = self.cover_client.cover_url_for(track)
                cover_url = self._cover_cache[identity]

            result = self.presence.update_lyrics(
                track,
                lyric_text,
                show_progress=self.config.show_progress,
                large_image=cover_url,
                large_text=track.album or track.title,
            )
            # Always advance the send clock so a hard Discord failure still backs off.
            self._last_sent_at = now
            if result == "sent":
                self._last_sent_lyric = lyric_text
                log.info("[discord] sent: %s", lyric_text)
            elif result == "skipped_unchanged":
                self._last_sent_lyric = lyric_text
                log.debug(
                    "[discord] skipped (unchanged payload): %s",
                    lyric_text,
                )
            else:
                self._pending_lyrics.insert(0, lyric_text)
                log.warning("[discord] send failed; will retry: %s", lyric_text)
            return

    def _with_lyric_lead(self, track: Track) -> Track:
        lead = max(self.config.lyric_lead_seconds, 0.0)
        if lead <= 0 or not track.playing:
            return track
        position = track.position_seconds + lead
        if track.duration_seconds and track.duration_seconds > 0:
            position = min(position, track.duration_seconds)
        return Track(
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration_seconds=track.duration_seconds,
            position_seconds=position,
            playing=track.playing,
            player=track.player,
        )

    def _lyrics_for(self, track: Track) -> Lyrics | None:
        identity = track.identity
        if identity in self._lyrics_cache:
            return self._lyrics_cache[identity]
        log.info("Fetching lyrics for %s — %s", track.artist, track.title)
        lyrics = self.lyrics_fetcher.fetch_for_track(track)
        self._lyrics_cache[identity] = lyrics
        if lyrics is None:
            log.info(
                "No synced lyrics found (tried local .lrc, Musixmatch, LRCLIB, NetEase). "
                "Apple Music in-app lyrics aren't directly readable; Musixmatch is the shared catalog."
            )
        elif lyrics.instrumental:
            log.info("Track is instrumental")
        elif lyrics.has_synced:
            log.info("Loaded %d synced lyric lines", len(lyrics.synced_lines))
        else:
            log.info("Only plain lyrics available; timed line sync disabled")
        return lyrics

    def _presence_text(self, track: Track, lyrics: Lyrics | None) -> str:
        lyric = self._active_lyric_text(track, lyrics)
        if lyric:
            return lyric
        if self.config.show_music_symbols:
            return self._music_only_text(track)
        return track.title

    def _music_only_text(self, track: Track) -> str:
        return format_music_only(
            track.position_seconds,
            self.config.music_symbols,
            self.config.music_symbol_interval_seconds,
            repeat=self.config.music_symbol_repeat,
        )

    def _active_lyric_text(self, track: Track, lyrics: Lyrics | None) -> str | None:
        if lyrics is None or lyrics.instrumental or not lyrics.has_synced:
            return None
        line, start, end = line_window(lyrics.synced_lines, track.position_seconds)
        if line is None or start is None or end is None:
            return None
        text = line.text.strip()
        if not text:
            return None
        return text
