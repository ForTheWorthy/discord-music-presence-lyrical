from lyrical_presence.models import Track
from lyrical_presence.normalize import normalize_track, search_title_variants


def test_splits_apple_music_artist_album_em_dash():
    track = Track(
        title="Good Life (feat. T-Pain)",
        artist="Kanye West — Graduation",
        album="",
    )
    normalized = normalize_track(track)
    assert normalized.artist == "Kanye West"
    assert normalized.album == "Graduation"
    assert normalized.title == "Good Life (feat. T-Pain)"


def test_splits_en_dash_and_hyphen_variants():
    assert normalize_track(Track("Song", "Artist – Album")).album == "Album"
    assert normalize_track(Track("Song", "Artist - Album")).album == "Album"


def test_keeps_explicit_album():
    track = Track("Song", "Artist — Something", album="Real Album")
    normalized = normalize_track(track)
    assert normalized.artist == "Artist — Something"
    assert normalized.album == "Real Album"


def test_title_variants_strip_feat():
    variants = search_title_variants("Good Life (feat. T-Pain)")
    assert variants[0] == "Good Life (feat. T-Pain)"
    assert "Good Life" in variants
