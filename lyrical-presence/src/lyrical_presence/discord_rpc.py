from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from lyrical_presence.models import Track
from lyrical_presence.textfit import split_lyric_for_presence

log = logging.getLogger(__name__)

# Discord Rich Presence string limits.
MAX_PRESENCE_CHARS = 128
# Activity `name` (used in "Listening to …") is shorter on some Discord clients.
MAX_NAME_CHARS = 128


class PresenceTransport(Protocol):
    def update(self, **payload: Any) -> None: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


class DiscordPresence:
    """Thin wrapper around pypresence with safe string handling."""

    def __init__(
        self,
        client_id: str,
        transport: PresenceTransport | None = None,
        *,
        status_display: str = "details",
        show_player_in_state: bool = False,
        max_lyric_chars: int = 40,
        min_update_interval_seconds: float = 1.0,
    ) -> None:
        self.client_id = client_id
        self._transport = transport
        self._connected = transport is not None
        self._last_payload: dict[str, Any] | None = None
        self._last_update_monotonic = 0.0
        self.status_display = status_display
        self.show_player_in_state = show_player_in_state
        self.max_lyric_chars = max_lyric_chars
        self.min_update_interval_seconds = min_update_interval_seconds

    def connect(self) -> None:
        if self._transport is not None:
            self._connected = True
            return
        from pypresence import Presence

        presence = Presence(self.client_id)
        presence.connect()
        self._transport = presence
        self._connected = True
        log.info("Connected to Discord IPC")

    def update_lyrics(
        self,
        track: Track,
        lyric_text: str | None,
        *,
        show_progress: bool = True,
        large_image: str | None = None,
        large_text: str | None = None,
    ) -> None:
        raw = " ".join((lyric_text or track.title).split())
        details, state_override = split_lyric_for_presence(
            raw,
            first_line_chars=self.max_lyric_chars,
            max_chars=MAX_PRESENCE_CHARS,
        )
        if state_override is None:
            state = self._state_for(
                track,
                has_lyric=bool(lyric_text),
                show_player=self.show_player_in_state,
            )
        else:
            # Overflow lyric continues on the second activity line.
            state = state_override

        payload: dict[str, Any] = {
            "details": details,
            "state": self._clip(state),
            # Under-username / Listening to uses the first line only (no timed cycling).
            "name": self._clip(details, max_chars=MAX_NAME_CHARS),
        }
        if large_image:
            payload["large_image"] = large_image
            payload["large_text"] = self._clip(large_text or track.album or track.title)
        activity_type = self._listening_activity_type()
        if activity_type is not None:
            payload["activity_type"] = activity_type
        status_display_type = self._status_display_type()
        if status_display_type is not None:
            payload["status_display_type"] = status_display_type
        if show_progress and track.duration_seconds and track.duration_seconds > 0:
            # Reconstruct timestamps from current position so Discord's bar stays accurate.
            now = time.time()
            start = now - max(track.position_seconds, 0.0)
            end = start + track.duration_seconds
            payload["start"] = int(start)
            payload["end"] = int(end)
        self._apply(payload)

    def update_fallback(self, track: Track, *, show_progress: bool = True) -> None:
        self.update_lyrics(track, None, show_progress=show_progress)

    def clear(self) -> None:
        if not self._connected or self._transport is None:
            return
        try:
            self._transport.clear()
            self._last_payload = None
            self._last_update_monotonic = 0.0
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to clear Discord presence: %s", exc)

    def close(self) -> None:
        if self._transport is None:
            return
        try:
            self.clear()
            close = getattr(self._transport, "close", None)
            if callable(close):
                close()
        except Exception as exc:  # noqa: BLE001
            log.debug("Discord presence close: %s", exc)
        finally:
            self._connected = False

    def _apply(self, payload: dict[str, Any]) -> None:
        if not self._connected or self._transport is None:
            raise RuntimeError("Discord presence is not connected")
        comparable = {
            key: value
            for key, value in payload.items()
            if key not in {"start", "end"}
        }
        last_comparable = None
        if self._last_payload is not None:
            last_comparable = {
                key: value
                for key, value in self._last_payload.items()
                if key not in {"start", "end"}
            }
        if comparable == last_comparable:
            return

        now = time.monotonic()
        # Avoid Discord IPC rate limits from rapid presence churn.
        if (
            self._last_payload is not None
            and self.min_update_interval_seconds > 0
            and (now - self._last_update_monotonic) < self.min_update_interval_seconds
        ):
            log.debug("Skipping presence update (rate-limit throttle)")
            return

        try:
            self._transport.update(**payload)
            self._last_payload = payload
            self._last_update_monotonic = now
            log.debug(
                "Presence updated: name=%r details=%r state=%r",
                payload.get("name"),
                payload.get("details"),
                payload.get("state"),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Discord presence update failed: %s", exc)

    def _status_display_type(self) -> Any | None:
        """Control which field appears after 'Listening to'."""
        try:
            from pypresence import StatusDisplayType
        except Exception:  # noqa: BLE001
            return {"details": 2, "state": 1, "name": 0}.get(self.status_display, 2)

        mapping = {
            "name": StatusDisplayType.NAME,
            "state": StatusDisplayType.STATE,
            "details": StatusDisplayType.DETAILS,
        }
        return mapping.get(self.status_display, StatusDisplayType.DETAILS)

    @staticmethod
    def _listening_activity_type() -> Any | None:
        try:
            from pypresence import ActivityType

            return ActivityType.LISTENING
        except Exception:  # noqa: BLE001 - optional dependency / older pypresence
            return 2

    @staticmethod
    def _state_for(track: Track, *, has_lyric: bool, show_player: bool) -> str:
        if has_lyric:
            base = f"{track.artist} — {track.title}"
        else:
            base = track.artist
        if show_player and track.player:
            return f"{base} · {track.player}"
        return base

    @staticmethod
    def _clip(text: str, max_chars: int = MAX_PRESENCE_CHARS) -> str:
        text = " ".join(text.split())
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"
