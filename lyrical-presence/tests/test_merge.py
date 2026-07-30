from lyrical_presence.discord_rpc import DiscordPresence
from lyrical_presence.lrclib import LrclibClient
from lyrical_presence.media import StaticTrackBackend
from lyrical_presence.merge import merge_short_lyric_lines
from lyrical_presence.models import Lyrics, LyricLine, Track
from lyrical_presence.service import LyricPresenceService, SyncConfig


def test_merge_short_lines_combines_subsecond_fragments():
    lines = (
        LyricLine(0.0, "Hello"),
        LyricLine(0.3, "world"),
        LyricLine(0.6, "how"),
        LyricLine(0.9, "are you"),
        LyricLine(2.5, "Fine"),
    )
    merged = merge_short_lyric_lines(lines, min_duration_seconds=1.0, separator=" ")
    assert merged == (
        LyricLine(0.0, "Hello world how are you"),
        LyricLine(2.5, "Fine"),
    )


def test_merge_short_lines_does_not_cross_empty_gap():
    lines = (
        LyricLine(0.0, "verse"),
        LyricLine(0.4, "one"),
        LyricLine(1.0, ""),
        LyricLine(5.0, "chorus"),
    )
    merged = merge_short_lyric_lines(lines, min_duration_seconds=1.0)
    assert merged[0] == LyricLine(0.0, "verse one")
    assert merged[1] == LyricLine(1.0, "")
    assert merged[2] == LyricLine(5.0, "chorus")


def test_merge_short_lines_respects_max_chars():
    lines = (
        LyricLine(0.0, "a" * 80),
        LyricLine(0.2, "b" * 80),
        LyricLine(0.4, "c" * 10),
    )
    merged = merge_short_lyric_lines(
        lines, min_duration_seconds=1.0, separator=" ", max_chars=100
    )
    assert len(merged) >= 2
    assert all(len(line.text) <= 100 for line in merged)


def test_merge_short_lines_noop_when_disabled_threshold():
    lines = (LyricLine(0.0, "a"), LyricLine(0.2, "b"))
    assert merge_short_lyric_lines(lines, min_duration_seconds=0) == lines


def test_service_merges_short_lines_before_presence_update():
    lines = (
        LyricLine(0.0, "one"),
        LyricLine(0.3, "two"),
        LyricLine(0.6, "three"),
        LyricLine(2.0, "four"),
    )
    lyrics = Lyrics(
        track_name="Song",
        artist_name="Artist",
        album_name="Album",
        duration=100,
        instrumental=False,
        synced_lines=lines,
    )

    def provider():
        return Track(
            title="Song",
            artist="Artist",
            duration_seconds=100,
            position_seconds=0.2,
            playing=True,
        )

    class FakeTransport:
        def __init__(self):
            self.updates = []

        def update(self, **payload):
            self.updates.append(payload)

        def clear(self):
            pass

        def close(self):
            pass

    class FakeLyricsClient(LrclibClient):
        def __init__(self):
            pass

        def fetch_for_track(self, track):
            return lyrics

    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    service = LyricPresenceService(
        media=StaticTrackBackend(provider),
        lyrics_client=FakeLyricsClient(),
        presence=presence,
        config=SyncConfig(
            show_progress=False,
            show_album_cover=False,
            lyric_lead_seconds=0,
            discord_min_interval_seconds=0,
            merge_short_lines=True,
            merge_lines_under_seconds=1.0,
            merge_line_separator=" / ",
        ),
    )
    service.tick()
    assert transport.updates[0]["details"] == "one / two / three"
