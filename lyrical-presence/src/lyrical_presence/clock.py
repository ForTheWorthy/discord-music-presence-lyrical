from __future__ import annotations

import time

from lyrical_presence.models import Track


class PlaybackClock:
    """Extrapolate playback position between sparse OS media updates.

    Windows SMTC (and some players) often refresh position only about once
    per second. Between those samples we advance by wall-clock time so lyric
    lines can switch on time.
    """

    def __init__(self, seek_threshold_seconds: float = 1.25) -> None:
        self.seek_threshold_seconds = seek_threshold_seconds
        self._identity: tuple[str, str, str] | None = None
        self._anchor_position = 0.0
        self._anchor_monotonic = 0.0
        self._playing = False

    def resolve(self, track: Track, *, now: float | None = None) -> Track:
        now = time.monotonic() if now is None else now
        identity = track.identity

        if identity != self._identity:
            self._identity = identity
            self._anchor_position = track.position_seconds
            self._anchor_monotonic = now
            self._playing = track.playing
            return track

        if not track.playing:
            self._anchor_position = track.position_seconds
            self._anchor_monotonic = now
            self._playing = False
            return track

        estimated = self._anchor_position + (now - self._anchor_monotonic)
        reported = track.position_seconds

        if abs(reported - estimated) > self.seek_threshold_seconds:
            position = reported
            self._anchor_position = reported
            self._anchor_monotonic = now
        elif reported >= self._anchor_position + 0.15:
            # Fresh advancing OS sample. Keep continuity if we were slightly ahead.
            position = max(estimated, reported)
            self._anchor_position = position
            self._anchor_monotonic = now
        else:
            # Stale OS sample — keep extrapolating from the last good anchor.
            position = estimated

        if track.duration_seconds and track.duration_seconds > 0:
            position = min(position, track.duration_seconds)

        self._playing = True
        return Track(
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration_seconds=track.duration_seconds,
            position_seconds=position,
            playing=track.playing,
            player=track.player,
        )
