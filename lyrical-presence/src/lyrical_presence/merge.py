from __future__ import annotations

from lyrical_presence.discord_rpc import MAX_PRESENCE_CHARS
from lyrical_presence.models import LyricLine


def merge_short_lyric_lines(
    lines: tuple[LyricLine, ...],
    *,
    min_duration_seconds: float = 1.0,
    separator: str = " ",
    max_chars: int = MAX_PRESENCE_CHARS,
) -> tuple[LyricLine, ...]:
    """Combine consecutive short timed lines into fewer, longer-lived lines.

    Providers often split one sentence across several sub-second cues. Merging
    those cues reduces Discord update pressure and skipped lines.

    Empty timed lines (instrumental gaps) are kept and never merged across.
    """
    if min_duration_seconds <= 0 or len(lines) <= 1:
        return lines

    max_chars = max(8, int(max_chars))
    separator = separator if separator is not None else " "
    merged: list[LyricLine] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        text = line.text.strip()
        if not text:
            merged.append(line)
            index += 1
            continue

        group_texts = [text]
        group_start = line.time_seconds
        cursor = index + 1

        while cursor < total:
            nxt = lines[cursor]
            nxt_text = nxt.text.strip()
            if not nxt_text:
                break

            # How long the current group would display if we stop before nxt.
            window = nxt.time_seconds - group_start
            if window >= min_duration_seconds:
                break

            candidate = separator.join([*group_texts, nxt_text])
            if len(candidate) > max_chars:
                break

            group_texts.append(nxt_text)
            cursor += 1

        combined = separator.join(group_texts)
        if len(combined) > max_chars:
            combined = combined[:max_chars]
        merged.append(LyricLine(time_seconds=group_start, text=combined))
        index = cursor

    return tuple(merged)
