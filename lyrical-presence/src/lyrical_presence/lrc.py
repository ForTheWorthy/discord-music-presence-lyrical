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
        # Keep empty timed lines — they mark instrumental / music-only gaps.
        time_seconds = minutes * 60 + seconds + fraction_seconds
        lines.append(LyricLine(time_seconds=time_seconds, text=text))

    lines.sort(key=lambda line: line.time_seconds)
    return tuple(lines)


def line_at(lines: tuple[LyricLine, ...], position_seconds: float) -> LyricLine | None:
    """Return the lyric line active at the given playback position."""
    current, _start, _end = line_window(lines, position_seconds)
    return current


def line_window(
    lines: tuple[LyricLine, ...],
    position_seconds: float,
) -> tuple[LyricLine | None, float | None, float | None]:
    """Return the active line plus its [start, end) playback window."""
    if not lines:
        return None, None, None
    current: LyricLine | None = None
    current_index = -1
    for index, line in enumerate(lines):
        if line.time_seconds <= position_seconds:
            current = line
            current_index = index
        else:
            break
    if current is None:
        return None, None, None
    start = current.time_seconds
    if current_index + 1 < len(lines):
        end = lines[current_index + 1].time_seconds
    else:
        # Hold the final line for a short window so trailing chunks can still cycle.
        end = start + 8.0
    return current, start, end
