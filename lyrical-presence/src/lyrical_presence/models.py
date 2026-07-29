from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Track:
    """Currently playing media track."""

    title: str
    artist: str
    album: str = ""
    duration_seconds: float | None = None
    position_seconds: float = 0.0
    playing: bool = True
    player: str = ""

    @property
    def identity(self) -> tuple[str, str, str]:
        return (
            self.title.strip().lower(),
            self.artist.strip().lower(),
            self.album.strip().lower(),
        )

    def is_valid(self) -> bool:
        return bool(self.title.strip() and self.artist.strip())


@dataclass(frozen=True, slots=True)
class LyricLine:
    """One timed lyric line."""

    time_seconds: float
    text: str


@dataclass(frozen=True, slots=True)
class Lyrics:
    """Synced and/or plain lyrics for a track."""

    track_name: str
    artist_name: str
    album_name: str
    duration: float | None
    instrumental: bool
    synced_lines: tuple[LyricLine, ...]
    plain_lyrics: str = ""

    @property
    def has_synced(self) -> bool:
        return bool(self.synced_lines)
