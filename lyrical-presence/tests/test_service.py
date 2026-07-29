from lyrical_presence.discord_rpc import DiscordPresence
from lyrical_presence.lrclib import LrclibClient
from lyrical_presence.media import StaticTrackBackend
from lyrical_presence.models import Lyrics, LyricLine, Track
from lyrical_presence.service import LyricPresenceService, SyncConfig


class FakeTransport:
    def __init__(self):
        self.updates = []
        self.cleared = 0
        self.closed = 0

    def update(self, **payload):
        self.updates.append(payload)

    def clear(self):
        self.cleared += 1

    def close(self):
        self.closed += 1


class FakeLyricsClient(LrclibClient):
    def __init__(self, lyrics: Lyrics | None):
        self._lyrics = lyrics

    def fetch_for_track(self, track: Track):
        return self._lyrics


def test_service_updates_presence_when_lyric_line_changes():
    lines = (
        LyricLine(0.0, "line one"),
        LyricLine(5.0, "line two"),
    )
    lyrics = Lyrics(
        track_name="Song",
        artist_name="Artist",
        album_name="Album",
        duration=100,
        instrumental=False,
        synced_lines=lines,
    )
    positions = iter([1.0, 1.5, 6.0])

    def provider():
        return Track(
            title="Song",
            artist="Artist",
            album="Album",
            duration_seconds=100,
            position_seconds=next(positions),
            playing=True,
            player="Spotify",
        )

    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    service = LyricPresenceService(
        media=StaticTrackBackend(provider),
        lyrics_client=FakeLyricsClient(lyrics),
        presence=presence,
        config=SyncConfig(show_progress=False),
    )

    service.tick()
    service.tick()
    service.tick()

    assert len(transport.updates) == 2
    assert transport.updates[0]["details"] == "line one"
    assert transport.updates[1]["details"] == "line two"
    assert "Artist — Song" in transport.updates[0]["state"]


def test_service_falls_back_to_music_symbols_when_no_lyrics():
    def provider():
        return Track("Song", "Artist", duration_seconds=90, position_seconds=10, playing=True)

    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    service = LyricPresenceService(
        media=StaticTrackBackend(provider),
        lyrics_client=FakeLyricsClient(None),
        presence=presence,
        config=SyncConfig(show_progress=False),
    )
    service.tick()
    assert transport.updates[0]["details"] == "♬ ♬ ♬"
    assert "Artist — Song" in transport.updates[0]["state"]


def test_service_shows_music_symbols_before_first_lyric_and_on_instrumental_gap():
    lines = (
        LyricLine(5.0, "verse"),
        LyricLine(10.0, ""),
        LyricLine(12.0, "chorus"),
    )
    lyrics = Lyrics(
        track_name="Song",
        artist_name="Artist",
        album_name="Album",
        duration=100,
        instrumental=False,
        synced_lines=lines,
    )
    positions = iter([1.0, 10.5, 12.5])

    def provider():
        return Track(
            title="Song",
            artist="Artist",
            duration_seconds=100,
            position_seconds=next(positions),
            playing=True,
        )

    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    service = LyricPresenceService(
        media=StaticTrackBackend(provider),
        lyrics_client=FakeLyricsClient(lyrics),
        presence=presence,
        config=SyncConfig(show_progress=False, music_symbol_interval_seconds=100),
    )
    service.tick()
    assert transport.updates[0]["details"] == "♪ ♪ ♪"

    service.tick()  # instrumental gap; same symbol so Discord payload is unchanged
    assert len(transport.updates) == 1

    service.tick()
    assert transport.updates[1]["details"] == "chorus"


def test_discord_presence_clips_long_strings():
    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    presence.connect()
    long_line = "x" * 200
    track = Track("Title", "Artist", duration_seconds=10, position_seconds=1, playing=True)
    presence.update_lyrics(track, long_line, show_progress=False)
    assert len(transport.updates[0]["details"]) == 128
    assert transport.updates[0]["details"].endswith("…")
