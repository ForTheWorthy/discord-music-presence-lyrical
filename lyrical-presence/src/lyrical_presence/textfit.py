from __future__ import annotations


def split_lyric_chunks(text: str, max_chars: int) -> tuple[str, ...]:
    """Split a lyric into word-wrapped chunks that each fit max_chars."""
    text = " ".join(text.split())
    if max_chars <= 0 or len(text) <= max_chars:
        return (text,) if text else ()

    words = text.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(word), max_chars):
                chunks.append(word[i : i + max_chars])
            continue
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return tuple(chunks)


def split_lyric_for_presence(
    text: str,
    *,
    first_line_chars: int,
    max_chars: int = 128,
) -> tuple[str, str | None]:
    """Split a long lyric across Discord details/state without timed cycling.

    Returns (details, state_override).
    state_override is None when the lyric fits on one line (caller keeps Artist — Title).
    """
    text = " ".join(text.split())
    if not text:
        return "", None
    if len(text) <= first_line_chars:
        return text, None

    chunks = split_lyric_chunks(text, first_line_chars)
    if not chunks:
        return "", None
    if len(chunks) == 1:
        return chunks[0][:max_chars], None

    details = chunks[0][:max_chars]
    remainder = " ".join(chunks[1:]).strip()
    if not remainder:
        return details, None
    if len(remainder) <= max_chars:
        return details, remainder
    return details, remainder[: max_chars - 1].rstrip() + "…"
