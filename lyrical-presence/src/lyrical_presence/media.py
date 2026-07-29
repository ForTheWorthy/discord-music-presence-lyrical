from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Callable

from lyrical_presence.models import Track

log = logging.getLogger(__name__)


class MediaBackend(ABC):
    """Reads currently playing media from the operating system."""

    @abstractmethod
    def current_track(self) -> Track | None:
        raise NotImplementedError


class NullMediaBackend(MediaBackend):
    def current_track(self) -> Track | None:
        return None


class PlayerctlBackend(MediaBackend):
    """Linux media backend using playerctl (MPRIS)."""

    def __init__(self, playerctl_bin: str = "playerctl") -> None:
        self.playerctl_bin = playerctl_bin

    def current_track(self) -> Track | None:
        status = self._run(["status"])
        if status is None:
            return None
        status = status.strip().lower()
        if status not in {"playing", "paused"}:
            return None

        title = self._meta("title")
        artist = self._meta("artist")
        if not title or not artist:
            return None

        album = self._meta("album") or ""
        length_us = self._meta("mpris:length")
        position = self._run(["position"])
        player = self._run(["--player", "%any", "metadata", "--format", "{{playerName}}"]) or ""

        duration_seconds = None
        if length_us and length_us.isdigit():
            # playerctl reports microseconds for mpris:length
            duration_seconds = int(length_us) / 1_000_000

        position_seconds = 0.0
        if position:
            try:
                position_seconds = float(position.strip())
            except ValueError:
                position_seconds = 0.0

        return Track(
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration_seconds,
            position_seconds=position_seconds,
            playing=status == "playing",
            player=player.strip(),
        )

    def _meta(self, key: str) -> str | None:
        return self._run(["metadata", key])

    def _run(self, args: list[str]) -> str | None:
        try:
            completed = subprocess.run(
                [self.playerctl_bin, *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("playerctl failed: %s", exc)
            return None
        if completed.returncode != 0:
            return None
        value = completed.stdout.strip()
        return value if value and value.lower() != "n/a" else None


class WindowsSmtcBackend(MediaBackend):
    """Windows media backend via GlobalSystemMediaTransportControlsSessionManager."""

    def current_track(self) -> Track | None:
        try:
            import asyncio

            from winsdk.windows.media.control import (  # type: ignore
                GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            )
        except ImportError:
            log.error(
                "Windows media support requires the 'winsdk' package. "
                "Install with: pip install winsdk"
            )
            return None

        async def _read() -> Track | None:
            manager = await MediaManager.request_async()
            session = manager.get_current_session()
            if session is None:
                return None
            info = await session.try_get_media_properties_async()
            timeline = session.get_timeline_properties()
            playback = session.get_playback_info()

            title = (info.title or "").strip()
            artist = (info.artist or "").strip()
            album = (info.album_title or "").strip()
            if not title or not artist:
                return None

            duration = timeline.end_time.total_seconds() if timeline.end_time else None
            position = timeline.position.total_seconds() if timeline.position else 0.0
            playing = int(playback.playback_status) == 4  # Playing

            return Track(
                title=title,
                artist=artist,
                album=album,
                duration_seconds=duration if duration and duration > 0 else None,
                position_seconds=position,
                playing=playing,
                player="Windows Media",
            )

        try:
            return asyncio.run(_read())
        except Exception as exc:  # noqa: BLE001 - OS bridge can raise many types
            log.warning("Windows SMTC read failed: %s", exc)
            return None


class MacosNowPlayingBackend(MediaBackend):
    """macOS media backend using media-control / osascript fallbacks."""

    def current_track(self) -> Track | None:
        if shutil.which("media-control"):
            track = self._from_media_control()
            if track:
                return track
        return self._from_osascript()

    def _from_media_control(self) -> Track | None:
        try:
            completed = subprocess.run(
                ["media-control", "get"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        # media-control outputs JSON-ish key=value lines in some versions;
        # prefer a minimal osascript path when parsing is ambiguous.
        return None

    def _from_osascript(self) -> Track | None:
        script = """
        tell application "System Events"
          set procList to name of every process
        end tell
        if procList contains "Music" then
          tell application "Music"
            if player state is playing or player state is paused then
              set t to name of current track
              set a to artist of current track
              set al to album of current track
              set d to duration of current track
              set p to player position
              set s to player state as string
              return t & "|||" & a & "|||" & al & "|||" & d & "|||" & p & "|||" & s
            end if
          end tell
        end if
        return ""
        """
        try:
            completed = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("osascript failed: %s", exc)
            return None
        raw = completed.stdout.strip()
        if not raw:
            return None
        parts = raw.split("|||")
        if len(parts) != 6:
            return None
        title, artist, album, duration, position, state = parts
        try:
            duration_seconds = float(duration)
            position_seconds = float(position)
        except ValueError:
            duration_seconds = None
            position_seconds = 0.0
        return Track(
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration_seconds,
            position_seconds=position_seconds,
            playing=state.strip().lower() == "playing",
            player="Music",
        )


def create_media_backend() -> MediaBackend:
    """Create the best available media backend for this platform."""
    if sys.platform.startswith("linux"):
        if shutil.which("playerctl"):
            return PlayerctlBackend()
        log.error(
            "Linux media detection requires playerctl. "
            "Install it (e.g. sudo apt install playerctl) and try again."
        )
        return NullMediaBackend()
    if sys.platform == "darwin":
        return MacosNowPlayingBackend()
    if sys.platform == "win32":
        return WindowsSmtcBackend()
    log.error("Unsupported platform: %s", sys.platform)
    return NullMediaBackend()


class StaticTrackBackend(MediaBackend):
    """Test helper backend that always returns a fixed track factory result."""

    def __init__(self, provider: Callable[[], Track | None]) -> None:
        self._provider = provider

    def current_track(self) -> Track | None:
        return self._provider()
