from __future__ import annotations

import re

from lyrical_presence.models import LyricLine

# [mm:ss.xx] or [mm:ss.xxx] or [mm:ss]
_LRC_LINE = re.compile(
    r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]\s*(.*)"
)


def parse_lrc(synced_lyrics: str | None) -> tuple[LyricLine, ...]:
    """Parse LRC-format synced lyrics into timed lines."""
    if not synced_lyrics or not synced_lyrics.strip():
        return ()

    lines: list[LyricLine] = []
    for raw in synced_lyrics.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        match = _LRC_LINE.fullmatch(raw)
        if not match:
            continue
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        fraction = match.group(3) or "0"
        # Normalize fractional seconds to milliseconds scale.
        if len(fraction) == 1:
            fraction_seconds = int(fraction) / 10
        elif len(fraction) == 2:
            fraction_seconds = int(fraction) / 100
        else:
            fraction_seconds = int(fraction) / 1000
        text = match.group(4).strip()
        if not text:
            continue
        time_seconds = minutes * 60 + seconds + fraction_seconds
        lines.append(LyricLine(time_seconds=time_seconds, text=text))

    lines.sort(key=lambda line: line.time_seconds)
    return tuple(lines)


def line_at(lines: tuple[LyricLine, ...], position_seconds: float) -> LyricLine | None:
    """Return the lyric line active at the given playback position."""
    if not lines:
        return None
    current: LyricLine | None = None
    for line in lines:
        if line.time_seconds <= position_seconds:
            current = line
        else:
            break
    return current
