from __future__ import annotations

import re

from lyrical_presence.models import Track

# Apple Music (and some other players) on Windows often report:
#   artist = "Kanye West — Graduation"
# with an empty album field.
_ARTIST_ALBUM_SPLIT = re.compile(
    r"\s+(?:—|–|-)\s+"
)
_FEAT_SUFFIX = re.compile(
    r"\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring)\s+.+$",
    re.IGNORECASE,
)


def normalize_track(track: Track) -> Track:
    """Clean OS media metadata into better lyrics-search fields."""
    title = " ".join(track.title.split()).strip()
    artist = " ".join(track.artist.split()).strip()
    album = " ".join(track.album.split()).strip()

    if not album:
        artist, album = _split_artist_album(artist)

    return Track(
        title=title,
        artist=artist,
        album=album,
        duration_seconds=track.duration_seconds,
        position_seconds=track.position_seconds,
        playing=track.playing,
        player=track.player,
    )


def search_title_variants(title: str) -> list[str]:
    """Return title variants useful for lyrics APIs."""
    variants: list[str] = []
    base = " ".join(title.split()).strip()
    if base:
        variants.append(base)
    stripped = _FEAT_SUFFIX.sub("", base).strip(" -–—")
    if stripped and stripped.lower() not in {v.lower() for v in variants}:
        variants.append(stripped)
    return variants


def _split_artist_album(artist: str) -> tuple[str, str]:
    parts = _ARTIST_ALBUM_SPLIT.split(artist, maxsplit=1)
    if len(parts) != 2:
        return artist, ""
    left, right = parts[0].strip(), parts[1].strip()
    if not left or not right:
        return artist, ""
    # Avoid splitting multi-artist credits like "Artist A - Artist B"
    # when the right side looks like another person rather than an album.
    # Prefer splitting when the right side is short-ish album-like text.
    if len(right) > 80:
        return artist, ""
    return left, right
