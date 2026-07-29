from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from lyrical_presence.models import Track

log = logging.getLogger(__name__)

# Discord Rich Presence string limits.
MAX_PRESENCE_CHARS = 128


class PresenceTransport(Protocol):
    def update(self, **payload: Any) -> None: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


class DiscordPresence:
    """Thin wrapper around pypresence with safe string truncation."""

    def __init__(self, client_id: str, transport: PresenceTransport | None = None) -> None:
        self.client_id = client_id
        self._transport = transport
        self._connected = transport is not None
        self._last_payload: dict[str, Any] | None = None

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
    ) -> None:
        details = self._clip(lyric_text or track.title)
        state = self._clip(self._state_for(track, has_lyric=bool(lyric_text)))
        payload: dict[str, Any] = {
            "details": details,
            "state": state,
        }
        activity_type = self._listening_activity_type()
        if activity_type is not None:
            payload["activity_type"] = activity_type
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
        try:
            self._transport.update(**payload)
            self._last_payload = payload
            log.debug("Presence updated: details=%r state=%r", payload.get("details"), payload.get("state"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Discord presence update failed: %s", exc)

    @staticmethod
    def _listening_activity_type() -> Any | None:
        try:
            from pypresence import ActivityType

            return ActivityType.LISTENING
        except Exception:  # noqa: BLE001 - optional dependency / older pypresence
            return 2

    @staticmethod
    def _state_for(track: Track, *, has_lyric: bool) -> str:
        if has_lyric:
            base = f"{track.artist} — {track.title}"
        else:
            base = track.artist
        if track.player:
            return f"{base} · {track.player}"
        return base

    @staticmethod
    def _clip(text: str) -> str:
        text = " ".join(text.split())
        if len(text) <= MAX_PRESENCE_CHARS:
            return text
        return text[: MAX_PRESENCE_CHARS - 1].rstrip() + "…"
