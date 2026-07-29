from __future__ import annotations

DEFAULT_MUSIC_SYMBOLS: tuple[str, ...] = ("♪", "♫", "♬", "♩")


def music_symbol_at(
    position_seconds: float,
    symbols: tuple[str, ...] = DEFAULT_MUSIC_SYMBOLS,
    interval_seconds: float = 1.5,
) -> str:
    """Pick a music symbol that advances with playback position."""
    if not symbols:
        return "♪"
    interval = interval_seconds if interval_seconds > 0 else 1.5
    index = int(max(position_seconds, 0.0) // interval) % len(symbols)
    return symbols[index]


def format_music_only(
    position_seconds: float,
    symbols: tuple[str, ...] = DEFAULT_MUSIC_SYMBOLS,
    interval_seconds: float = 1.5,
    *,
    repeat: int = 3,
) -> str:
    """Build a short music-only presence line, e.g. '♪ ♪ ♪'."""
    symbol = music_symbol_at(position_seconds, symbols, interval_seconds)
    count = max(1, repeat)
    return " ".join([symbol] * count)
