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


def chunk_at_progress(
    chunks: tuple[str, ...],
    *,
    elapsed_seconds: float,
    window_seconds: float,
) -> str:
    """Pick which chunk to show based on progress through the lyric window."""
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0]
    window = max(window_seconds, 0.5)
    elapsed = max(elapsed_seconds, 0.0)
    # Divide the available window evenly across chunks.
    slot = window / len(chunks)
    index = int(elapsed / slot)
    if index >= len(chunks):
        index = len(chunks) - 1
    return chunks[index]
